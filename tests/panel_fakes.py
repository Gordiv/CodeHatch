"""Stand-ins for the tests of the panels: a server with a staff role, a player without one and an administrator, a team
channel, and interactions whose messages are real objects (an id, delete/edit), so the timers of the windows and the
answers "in place" can be followed.

No unittest here, so the same file also runs inside the temporary copy of the bot used by tests/click_driver.py."""
import itertools

import discord

from tests import fakes

STAFF, OTHER, EVERYONE_ID = 300, 301, 4242
_ids = itertools.count(90_000)


def not_found(text: str = "Unknown Message") -> discord.NotFound:
    return discord.NotFound(type("R", (), {"status": 404, "reason": "Not Found"})(), text)


class Role:
    permissions = discord.Permissions.none()

    def __init__(self, role_id, name="role", default=False, managed=False, members=0):
        self.id, self.name, self.position = role_id, name, role_id
        self.mention = "@everyone" if default else f"<@&{role_id}>"
        self.managed, self._default, self.members = managed, default, [object()] * members

    def is_default(self):
        return self._default

    def __ge__(self, other):  # "a role at or above the bot's top role" is checked when roles are handed out
        return self.position >= other.position


class Member:
    """A person who is not an administrator, with the given roles."""
    mention, display_name = "<@50>", "Mod"
    guild_permissions = discord.Permissions.none()

    def __init__(self, roles=(), user_id=50):
        self.roles, self.id = list(roles), user_id

    def __str__(self):
        return "mod#0"


class Message:
    """A message the bot can delete or edit (until `locked`: Discord no longer lets it, like after 15 minutes)."""

    def __init__(self, message_id=None, locked=False):
        self.id = message_id if message_id is not None else next(_ids)
        self.deleted, self.edits, self.locked, self.delete_calls = False, [], locked, 0

    async def delete(self):
        self.delete_calls += 1
        if self.locked or self.deleted:
            raise not_found("Unknown Webhook")
        self.deleted = True

    async def edit(self, **kwargs):
        if self.locked or self.deleted:
            raise not_found("Unknown Webhook")
        self.edits.append(kwargs)


class PartialMessage:
    def __init__(self, channel, message_id):
        self.channel, self.id = channel, message_id

    async def edit(self, **kwargs):
        if self.id in self.channel.deleted:
            raise not_found()
        fakes.check_payload(kwargs.get("content"), kwargs.get("embed"), None, kwargs.get("view"), "panel edit")
        self.channel.edits.append((self.id, kwargs))

    async def delete(self):
        self.channel.deleted.add(self.id)


class TextChannel:
    def __init__(self, channel_id, can_send=True):
        self.id, self.mention, self.can_send = channel_id, f"<#{channel_id}>", can_send
        self.sent, self.edits, self.deleted, self.next_id = [], [], set(), channel_id * 1000

    def permissions_for(self, member):
        return discord.Permissions(view_channel=self.can_send, send_messages=self.can_send, embed_links=self.can_send)

    def overwrites_for(self, role):
        return discord.PermissionOverwrite()

    async def send(self, content=None, **kwargs):
        fakes.check_payload(content or kwargs.get("content"), kwargs.get("embed"), None, kwargs.get("view"), "panel post")
        self.next_id += 1
        self.sent.append(dict(kwargs, content=content) if content is not None else kwargs)
        return Message(self.next_id)

    def get_partial_message(self, message_id):
        return PartialMessage(self, message_id)


class ChannelMap(dict):
    """guild.channels is a list in discord.py; here it can also be looked up by id (iterating gives the channels)."""

    def __iter__(self):
        return iter(self.values())


class Guild:
    id, owner_id = 4242, 1

    def __init__(self, roles=(), channels=()):
        self.roles = {r.id: r for r in roles}
        self.channels = ChannelMap((c.id, c) for c in channels)
        self.me = type("Me", (), {"top_role": Role(10_000, "Bot"), "id": 99, "mention": "<@99>",
                                  "guild_permissions": discord.Permissions.all()})()
        self.member_count = 100
        self.name = "Test server"
        self.system_channel = None

    def get_role(self, role_id):
        return self.roles.get(role_id)

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)

    def get_member(self, user_id):
        return None


class LiveFollowup(fakes.Followup):
    def __init__(self, response, interaction):
        super().__init__(response)
        self.interaction = interaction

    async def send(self, content=None, **kwargs):
        wait = kwargs.get("wait")
        await super().send(content, **kwargs)
        message = Message()
        self.interaction.messages_made.append(message)
        return message if wait else None


class LiveClient(fakes.Client):
    """The bot as the windows see it (interaction.client): on no server but this one, owned by an administrator."""
    guilds = ()
    user = type("BotUser", (), {"id": 99, "mention": "<@99>", "name": "Bot"})()
    latency = 0.05

    def get_guild(self, guild_id):
        return None

    def get_channel(self, channel_id):
        return None

    async def application_info(self):
        owner = type("Owner", (), {"id": fakes.Admin.id})()
        return type("AppInfo", (), {"team": None, "owner": owner, "bot_public": False})()


class LiveInteraction(fakes.Interaction):
    """An interaction from a click on `message` (None: from a command or from a form not opened from a message).
    gone: that message was removed meanwhile, so editing it fails like in Discord."""

    def __init__(self, guild=None, user=None, message=None, gone=False, **cogs):
        super().__init__(**cogs)
        if guild is not None:
            self.guild, self.guild_id = guild, guild.id
        if user is not None:
            self.user = user
        self.client = LiveClient(**cogs)
        self.message, self.gone, self.data = message, gone, {}
        self.channel = guild.get_channel(700) if guild is not None else None  # the team channel
        self.messages_made = []
        self.followup = LiveFollowup(self.response, self)

    async def original_response(self):
        message = Message()
        self.messages_made.append(message)
        return message

    async def edit_original_response(self, **kwargs):
        if self.gone:
            if not self.response.done:
                fakes._fail("edit_original_response before the interaction was answered")
            raise not_found()
        await super().edit_original_response(**kwargs)
        return Message(self.message.id if self.message is not None else None)

    async def delete_original_response(self):
        if self.gone:
            raise not_found()
        await super().delete_original_response()


def make_guild(staff_ids=()):
    """A server with a staff role (300), a role every player has (301) and @everyone, plus a team channel (700)."""
    from utils import access, config_store
    guild = Guild([Role(STAFF, "Game moderator", members=3), Role(OTHER, "Player", members=90),
                   Role(EVERYONE_ID, "@everyone", default=True)], [TextChannel(700)])
    guild.default_role = guild.roles[EVERYONE_ID]
    if staff_ids:
        config_store.set_guild_values(guild.id, access.GAME_PANEL, {"staff_role_ids": list(staff_ids)})
    return guild


def staff_member(guild) -> Member:
    return Member([guild.roles[EVERYONE_ID], guild.roles[STAFF]])


def player_member(guild) -> Member:
    return Member([guild.roles[EVERYONE_ID], guild.roles[OTHER]], user_id=51)


def interaction_for(guild, who: str, **kwargs) -> LiveInteraction:
    """who: "admin", "staff" (a member with the staff role), "player" (nobody special)."""
    user = {"admin": lambda: fakes.Admin(), "staff": lambda: staff_member(guild), "player": lambda: player_member(guild)}[who]()
    user.guild = guild  # a member knows its server
    return LiveInteraction(guild=guild, user=user, **kwargs)
