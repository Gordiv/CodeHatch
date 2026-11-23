"""The game control panel: one message in the staff channel with buttons for the game (promo codes, the player card
with bans, gifts, announcements, events, eggs). Each button opens a window only the clicking person sees.

Who: administrators, and the roles an administrator chose in /setup-roblox -> Control panel (checked at every click,
so taking a role off the list works at once). Choosing the roles and posting the panel stay admin-only, the same way
an administrator decides which roles members may take on a role panel.

The buttons keep working after a restart (a view without a timeout and with fixed custom IDs, registered at start),
and the posted message is redrawn at start when the bot's language or the chosen roles changed.
"""
import hashlib
import json
import logging
import time

import discord
from discord.ext import commands

from utils import access, config_store
from utils.i18n import t
from utils.ui import AdminView, CloseView, send_panel, staff_only

log = logging.getLogger("game_panel")
SECTION = access.GAME_PANEL
MAX_ROLES = 25
MANAGER_ENTRY = "ManagerAccess"  # the game reads who may open its ⚙️ Manager from this DataStore entry
LIVE_KEYS = {"gift", "announce", "events", "eggs"}  # need cogs/live_game.py
# the permission (/setup -> 🛡️ Permissions) each button needs
BUTTON_PERMISSIONS = {"codes": "codes", "player": "players", "gift": "gifts", "announce": "announce", "events": "events",
                      "eggs": "eggs"}

# (key, emoji, label, what it does, row)
BUTTONS = [
    ("codes", "📜", "rbx.btn_codes", "gpanel.help_codes", 0),
    ("player", "👤", "rbx.btn_player", "gpanel.help_player", 0),
    ("gift", "🎁", "rbx.btn_gift", "gpanel.help_gift", 0),
    ("announce", "📢", "rbx.btn_announce", "gpanel.help_announce", 1),
    ("events", "⚡", "rbx.btn_events", "gpanel.help_events", 1),
    ("eggs", "🥚", "rbx.btn_eggs", "gpanel.help_eggs", 1),
]


def _color() -> int:
    return config_store.embed_color()


def settings(guild_id: int) -> dict:
    cfg = {"staff_role_ids": [], "channel_id": 0, "message_id": 0, "drawn": ""}
    try:
        cfg.update(config_store.guild_section(guild_id, SECTION))
    except config_store.ConfigError:
        pass
    return cfg


def save(guild_id: int, **changes):
    config_store.set_guild_values(guild_id, SECTION, changes)


def panel_channel(guild: discord.Guild, channel_id):
    """The channel (or thread: a panel may be posted in one) the panel is in."""
    getter = getattr(guild, "get_channel_or_thread", None) or guild.get_channel
    return getter(channel_id or 0)


def staff_roles(guild: discord.Guild) -> list:
    roles = [guild.get_role(role_id) for role_id in access.staff_role_ids(guild.id)]
    return sorted([r for r in roles if r], key=lambda r: r.position, reverse=True)


def help_lines() -> str:
    return "\n".join(f"{emoji} **{t(label)}** – {t(help_key)}" for _, emoji, label, help_key, _ in BUTTONS)


def panel_embed(guild: discord.Guild) -> discord.Embed:
    """The posted panel (seen by everyone in the staff channel)."""
    roles = staff_roles(guild)
    who = t("gpanel.who", roles=", ".join(r.mention for r in roles)) if roles else t("gpanel.who_admins_only")
    embed = discord.Embed(title=t("gpanel.title"), description=f"{t('gpanel.description')}\n\n{who}"[:4096], color=_color())
    embed.add_field(name=t("gpanel.buttons_title"), value=help_lines()[:1024], inline=False)
    embed.set_footer(text=t("gpanel.footer"))
    return embed


class GamePanelView(discord.ui.View):
    """The posted panel: no timeout and fixed custom IDs, so it works after a restart (bot.add_view in setup)."""

    def __init__(self):
        super().__init__(timeout=None)
        for key, emoji, label, _, row in BUTTONS:
            button = discord.ui.Button(label=t(label)[:80], emoji=emoji, style=discord.ButtonStyle.success,
                                       custom_id=f"gpanel:{key}", row=row)
            button.callback = self._opener(key)
            self.add_item(button)

    @staticmethod
    def _opener(key: str):
        async def callback(interaction: discord.Interaction):
            await open_action(key, interaction)
        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if access.is_game_staff(interaction):
            return True
        await interaction.response.send_message(t("gpanel.no_access"), ephemeral=True)
        return False


async def open_action(key: str, interaction: discord.Interaction):
    """What a panel button opens: the same windows as /setup-roblox, only for the person who clicked. setup_roblox is
    imported here, on click: the bot loads it as an extension after this module, and one copy of it must exist."""
    from cogs import setup_roblox
    if not await staff_only(interaction, BUTTON_PERMISSIONS[key]):
        return
    if key in LIVE_KEYS and setup_roblox.live_game is None:  # cogs/live_game.py broken or missing
        await interaction.response.send_message(t("errors.unexpected"), ephemeral=True)
        return
    if key in ("codes", "events", "eggs"):
        await interaction.response.defer(ephemeral=True, thinking=True)
        view = {"codes": setup_roblox.CodesView, "events": setup_roblox.EventsView, "eggs": setup_roblox.EggsView}[key]()
        await send_panel(interaction, view, embed=await view.embed())
    elif key == "gift":
        await interaction.response.send_modal(setup_roblox.GiftModal())
    elif key == "announce":
        await interaction.response.send_modal(setup_roblox.AnnounceModal())
    elif key == "player":
        await setup_roblox.open_player_lookup(interaction)


def _signature(guild: discord.Guild) -> str:
    """What the posted panel shows: when it changes (language, roles), the message is redrawn at start."""
    data = {"embed": panel_embed(guild).to_dict(), "buttons": [c.to_component_dict() for c in GamePanelView().children]}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


async def redraw_posted(guild: discord.Guild, force: bool = True) -> bool:
    """Draws the posted panel again (new roles or language). False when there is no panel any more."""
    cfg = settings(guild.id)
    channel = panel_channel(guild, cfg["channel_id"])
    if not channel or not cfg["message_id"]:
        return False
    signature = _signature(guild)
    if not force and cfg.get("drawn") == signature:
        return True
    try:
        await channel.get_partial_message(cfg["message_id"]).edit(embed=panel_embed(guild), view=GamePanelView())
    except discord.NotFound:
        save(guild.id, message_id=0)  # deleted by someone: the manager then says it isn't posted
        return False
    except discord.HTTPException as e:
        log.warning("Could not redraw the game control panel in %s: %s", guild.id, e)
        return False
    save(guild.id, drawn=signature)
    return True


async def post_panel(interaction: discord.Interaction) -> str:
    """Posts the panel in the current channel and removes the previous one (one panel per server). Returns the
    message for the administrator."""
    guild, channel = interaction.guild, interaction.channel
    permissions = channel.permissions_for(guild.me)
    if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
        return t("gpanel.err_cant_send")
    try:
        message = await channel.send(embed=panel_embed(guild), view=GamePanelView(),
                                     allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        return t("gpanel.err_cant_send")
    old = settings(guild.id)
    save(guild.id, channel_id=channel.id, message_id=message.id, drawn=_signature(guild))
    text = t("gpanel.posted", channel=channel.mention)
    everyone = getattr(guild, "default_role", None)
    if everyone is not None and channel.permissions_for(everyone).view_channel:
        text += "\n" + t("gpanel.warn_public_channel")  # nobody else can use it, but players see it
    if old["message_id"] and old["message_id"] != message.id and old["channel_id"]:
        old_channel = panel_channel(guild, old["channel_id"])
        try:
            if old_channel is None:  # e.g. an archived thread
                old_channel = await interaction.client.fetch_channel(old["channel_id"])
            await old_channel.get_partial_message(old["message_id"]).delete()
            text += "\n" + t("gpanel.old_removed", channel=old_channel.mention)
        except discord.NotFound:
            pass  # someone deleted it already
        except (discord.HTTPException, AttributeError):
            # no access there any more: the old panel still checks access on every click, the admin may delete it
            text += "\n" + t("gpanel.old_not_removed",
                              link=f"https://discord.com/channels/{guild.id}/{old['channel_id']}/{old['message_id']}")
    return text


async def role_problem(guild: discord.Guild, role) -> str:
    """Why this role can't open the control panel (None = it can): @everyone or an app's role would let anyone ban and
    hand out rewards."""
    if role.is_default() or role.managed:
        return t("gpanel.err_role", role=role.mention)
    return None


def big_role(guild: discord.Guild, role) -> bool:
    """A role a big part of the server has (a mistake, most likely)."""
    total = getattr(guild, "member_count", 0) or 0
    return len(role.members) > max(10, total // 4)


# ---------- Settings (/setup-roblox -> Control panel, administrators only) ----------

class StaffRolesSelect(discord.ui.RoleSelect):
    def __init__(self, manager: "GamePanelManager", current: list):
        current = current[:MAX_ROLES]  # Discord refuses more preselected roles than the menu may take
        super().__init__(placeholder=t("gpanel.roles_placeholder"), min_values=0, max_values=MAX_ROLES,
                         default_values=[discord.Object(id=r.id) for r in current], row=0)
        self.manager = manager
        self.shown = {r.id for r in current}  # what this menu showed: only the admin's own changes are saved

    async def callback(self, interaction: discord.Interaction):
        chosen, skipped = set(), []
        for role in self.values:
            problem = await role_problem(interaction.guild, role)
            if problem:
                skipped.append(problem)
            else:
                chosen.add(role.id)
        picked = {role.id for role in self.values}
        # another admin may have changed the list since this menu was opened: keep their changes
        current = set(access.staff_role_ids(interaction.guild_id))
        result = (current - (self.shown - picked)) | (chosen - self.shown)
        result -= picked - chosen  # a role that may not open the panel is never kept
        perms = access.role_permissions(interaction.guild_id)
        # a role added here may do everything, as before; what each role may do is changed in /setup -> 🛡️ Permissions.
        # Roles this menu doesn't show (added in 🛡️ with nothing ticked yet) stay as they are.
        kept = {role_id: p for role_id, p in perms.items() if role_id not in self.shown and role_id not in picked}
        kept.update({role_id: perms[role_id] if perms.get(role_id) else list(access.PERMISSIONS) for role_id in result})
        access.set_role_permissions(interaction.guild_id, kept)
        await self.manager.refresh(interaction)  # Discord waits only 3 s for the first answer
        await redraw_posted(interaction.guild)
        if skipped:
            await send_panel(interaction, CloseView(), content="\n".join(skipped)[:1900],
                             allowed_mentions=discord.AllowedMentions.none())


class GamePanelManager(AdminView):
    """Which roles may use the control panel, and posting it in the current channel."""

    def __init__(self, guild: discord.Guild):
        super().__init__()
        self.guild = guild
        self.post.label = t("gpanel.btn_post")
        self.permissions.label = t("perm.btn_roles")
        self._build()

    def _build(self):
        for item in [i for i in self.children if isinstance(i, discord.ui.RoleSelect)]:
            self.remove_item(item)
        self.add_item(StaffRolesSelect(self, staff_roles(self.guild)))

    def embed(self) -> discord.Embed:
        guild, cfg = self.guild, settings(self.guild.id)
        roles = staff_roles(guild)
        embed = discord.Embed(title=t("gpanel.title"), description=t("gpanel.manager_description"), color=_color())
        embed.add_field(name=t("gpanel.can_title"), value=f"{help_lines()}\n\n{t('gpanel.warn_bans')}"[:1024], inline=False)
        embed.add_field(name=t("gpanel.roles_field", count=len(roles)),
                        value="\n".join(f"{r.mention} · {len(r.members)} 👤{' ⚠️' if big_role(guild, r) else ''}"
                                        for r in roles)[:1024] or t("gpanel.roles_none"), inline=False)
        if any(big_role(guild, r) for r in roles):
            embed.add_field(name="⚠️", value=t("gpanel.warn_big_role"), inline=False)
        channel = panel_channel(guild, cfg["channel_id"])
        if channel and cfg["message_id"]:
            where = t("gpanel.where_posted", channel=channel.mention,
                      link=f"https://discord.com/channels/{guild.id}/{channel.id}/{cfg['message_id']}")
        else:
            where = t("gpanel.where_none")
        embed.add_field(name=t("gpanel.where_field"), value=where, inline=False)
        embed.set_footer(text=t("gpanel.manager_footer"))
        return embed

    async def refresh(self, interaction: discord.Interaction):
        self.guild = interaction.guild
        self._build()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="What each role may do", emoji="🛡️", style=discord.ButtonStyle.primary, row=1)
    async def permissions(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_role_permissions(interaction)

    @discord.ui.button(label="Post the panel here", emoji="📤", style=discord.ButtonStyle.success, row=1)
    async def post(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        text = await post_panel(interaction)
        await send_panel(interaction, CloseView(), content=text, allowed_mentions=discord.AllowedMentions.none())
        if self.message is not None:  # the settings now show where the panel is
            try:
                await self.message.edit(embed=self.embed(), view=self)
            except (discord.HTTPException, ValueError):
                pass


# ---------- 🛡️ Permissions (/setup, administrators only) ----------
# Discord: the roles with access to the game actions, and for each role what it may do. The game: the Roblox players
# (besides the game's owner) who may open the ⚙️ Manager, and for each what they may do there.

def whole_lines(lines: list, limit: int) -> str:
    """As many whole lines as fit, then "… +N" (a field never ends mid-line)."""
    shown = []
    for i, line in enumerate(lines):
        rest = len(lines) - i
        if len("\n".join(shown + [line])) + len(f"\n… +{rest}") > limit:
            return "\n".join(shown + [f"… +{rest}"])
        shown.append(line)
    return "\n".join(shown)


def permission_names(perms, allowed=None) -> str:
    perms = [p for p in (allowed or access.GAME_PERMISSIONS) if p in set(perms)]
    return ", ".join(f"{access.PERMISSION_EMOJI[p]} {t(f'perm.{p}')}" for p in perms) or t("perm.nothing")


def permission_options(current, allowed) -> list:
    return [discord.SelectOption(label=t(f"perm.{p}")[:100], value=p, emoji=access.PERMISSION_EMOJI[p],
                                 description=t(f"perm.{p}_help")[:100], default=p in set(current)) for p in allowed]


class PermissionsHubView(AdminView):
    """/setup -> 🛡️ Permissions: two windows, Discord roles and the game's Manager."""

    def __init__(self):
        super().__init__()
        self.roles.label = t("perm.btn_roles")
        self.game.label = t("perm.btn_game")

    @staticmethod
    def embed() -> discord.Embed:
        embed = discord.Embed(title=t("perm.title"), description=t("perm.hub_description"), color=_color())
        return embed

    @discord.ui.button(label="Discord roles", emoji="💬", style=discord.ButtonStyle.primary, row=0)
    async def roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_role_permissions(interaction)

    @discord.ui.button(label="Manager in the game", emoji="🎮", style=discord.ButtonStyle.success, row=0)
    async def game(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_manager_users(interaction)


async def send_permissions(interaction: discord.Interaction):
    await send_panel(interaction, PermissionsHubView(), embed=PermissionsHubView.embed())


class AccessRolesSelect(discord.ui.RoleSelect):
    """Which roles have access to the game actions at all (what each may do is ticked below)."""

    def __init__(self, view: "RolePermissionsView", current: list):
        current = current[:MAX_ROLES]
        super().__init__(placeholder=t("perm.roles_placeholder"), min_values=0, max_values=MAX_ROLES,
                         default_values=[discord.Object(id=r) for r in current], row=0)
        self.panel = view
        self.shown = set(current)

    async def callback(self, interaction: discord.Interaction):
        skipped, chosen = [], set()
        for role in self.values:
            problem = await role_problem(interaction.guild, role)
            if problem:
                skipped.append(problem)
            else:
                chosen.add(role.id)
        perms = access.role_permissions(interaction.guild_id)
        picked = {role.id for role in self.values}
        for role_id in self.shown - picked:  # taken off the list by the admin
            perms.pop(role_id, None)
        for role_id in chosen - set(perms):  # a new role starts with nothing: the admin ticks what it may do
            perms[role_id] = []
        access.set_role_permissions(interaction.guild_id, perms)
        new = [role_id for role_id in chosen if role_id not in self.shown]
        if new:
            self.panel.selected = new[0]
        await self.panel.refresh(interaction)
        await redraw_posted(interaction.guild)
        if skipped:
            await send_panel(interaction, CloseView(), content="\n".join(skipped)[:1900],
                             allowed_mentions=discord.AllowedMentions.none())


class PickRoleSelect(discord.ui.Select):
    def __init__(self, view: "RolePermissionsView", roles: list):
        options = [discord.SelectOption(label=f"@{role.name}"[:100], value=str(role.id), default=role.id == view.selected)
                   for role in roles[:25]]
        super().__init__(placeholder=t("perm.pick_role"), min_values=1, max_values=1, options=options, row=1)
        self.panel = view

    async def callback(self, interaction: discord.Interaction):
        self.panel.selected = int(self.values[0])
        await self.panel.refresh(interaction)


class RolePermissionSelect(discord.ui.Select):
    def __init__(self, view: "RolePermissionsView", current: list):
        super().__init__(placeholder=t("perm.pick_permissions"), min_values=0, max_values=len(access.PERMISSIONS),
                         options=permission_options(current, access.PERMISSIONS), row=2)
        self.panel = view

    async def callback(self, interaction: discord.Interaction):
        perms = access.role_permissions(interaction.guild_id)
        if self.panel.selected in perms:
            perms[self.panel.selected] = list(self.values)
            access.set_role_permissions(interaction.guild_id, perms)
        await self.panel.refresh(interaction)
        await redraw_posted(interaction.guild)


class RolePermissionsView(AdminView):
    """The roles with access and, for the role picked in the second list, what it may do (ticked in the third)."""

    def __init__(self, guild: discord.Guild):
        super().__init__()
        self.guild = guild
        self.selected = None
        self._build()

    def roles(self) -> list:
        found = [self.guild.get_role(role_id) for role_id in access.role_permissions(self.guild.id)]
        return sorted([r for r in found if r], key=lambda r: r.position, reverse=True)

    def _build(self):
        for item in [i for i in self.children if not isinstance(i, discord.ui.Button)]:
            self.remove_item(item)
        roles = self.roles()
        if roles and self.selected not in {r.id for r in roles}:
            self.selected = roles[0].id
        self.add_item(AccessRolesSelect(self, [r.id for r in roles]))
        if roles:
            self.add_item(PickRoleSelect(self, roles))
            self.add_item(RolePermissionSelect(self, access.role_permissions(self.guild.id).get(self.selected, [])))

    def embed(self) -> discord.Embed:
        embed = discord.Embed(title=t("perm.roles_title"), description=t("perm.roles_description"), color=_color())
        perms = access.role_permissions(self.guild.id)
        lines = []
        for role in self.roles():
            mark = "👉 " if role.id == self.selected else ""
            warn = " ⚠️" if big_role(self.guild, role) else ""
            lines.append(f"{mark}{role.mention} · {len(role.members)} 👤{warn}\n└ {permission_names(perms.get(role.id, []), access.PERMISSIONS)}")
        embed.add_field(name=t("perm.roles_field"), value=whole_lines(lines, 1024) or t("perm.roles_none"), inline=False)
        if any(big_role(self.guild, r) for r in self.roles()):
            embed.add_field(name="⚠️", value=t("gpanel.warn_big_role"), inline=False)
        embed.set_footer(text=t("perm.roles_footer"))
        return embed

    async def refresh(self, interaction: discord.Interaction):
        self.guild = interaction.guild
        self._build()
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=self.embed(), view=self)
        else:
            await interaction.response.edit_message(embed=self.embed(), view=self)


async def send_role_permissions(interaction: discord.Interaction):
    view = RolePermissionsView(interaction.guild)
    await send_panel(interaction, view, embed=view.embed(), allowed_mentions=discord.AllowedMentions.none())


# ---------- The game's ⚙️ Manager: who besides the game's owner, and what each may do ----------

async def change_manager_access(change=None) -> str:
    """Changes the list (change(users) -> users) and sends it to the game (DataStore entry ManagerAccess, then a notice
    so every server reads it at once). The game's owner may change the same list in the Manager's 🛡️ tab: the entry
    is read first and saved only if nobody changed it in between (otherwise read again), so neither side undoes the
    other. Returns "" when it worked, otherwise the reason. When the game isn't connected yet, the change is kept here
    and goes on the next send; when Roblox can't be read, nothing is changed (the old list could undo the game's)."""
    from utils import open_cloud  # needs the game sync settings, loaded only when used
    try:
        store = open_cloud.live_settings()["datastore"]
    except Exception as e:  # not set up yet
        if change:
            access.set_manager_users(change(access.manager_users()))
        return str(e)[:300] or type(e).__name__
    try:
        for attempt in range(3):
            entry, version = await open_cloud.read_entry_versioned(store, MANAGER_ENTRY)
            # after a conflict the game's list is newer than the change just made here: it is taken as it is
            access.adopt_manager_entry(entry, force=attempt > 0)
            if change:
                access.set_manager_users(change(access.manager_users()))
            try:
                await open_cloud.write_entry_if(store, MANAGER_ENTRY, access.manager_access_entry(), version)
            except open_cloud.VersionConflict:
                continue  # saved in the game in that moment: read again and apply the change to that list
            await open_cloud.publish({"type": "access", "at": int(time.time())})
            return ""
        return t("perm.busy")
    except Exception as e:  # Roblox refused or didn't answer
        return str(e)[:300] or type(e).__name__


async def push_manager_access() -> str:
    """Sends the list as it is (📤 Send to the game)."""
    return await change_manager_access()


async def pull_manager_access() -> bool:
    """Reads the list from the game first: the game's owner may have changed it in the Manager's 🛡️ tab, and a change
    here must not undo that. Returns True when the list here changed. Quiet when the game isn't connected yet."""
    from utils import open_cloud
    try:
        entry = await open_cloud.read_entry(open_cloud.live_settings()["datastore"], MANAGER_ENTRY)
    except Exception as e:  # not set up yet, Roblox didn't answer: the list here is used
        log.info("Could not read the Manager list from the game: %s", e)
        return False
    before = access.manager_users()
    return access.adopt_manager_entry(entry) and access.manager_users() != before


class AddManagerUserModal(discord.ui.Modal):
    def __init__(self, view: "ManagerUsersView"):
        super().__init__(title=t("perm.add_title"))
        self.panel = view
        self.username = discord.ui.TextInput(label=t("perm.add_label"), placeholder=t("perm.add_ph"), max_length=40)
        self.add_item(self.username)

    async def on_submit(self, interaction: discord.Interaction):
        from utils import roblox_api
        if not access.is_admin(interaction):  # the rights may have been taken away while the form was open
            await interaction.response.send_message(t("errors.admin_only"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            found = await roblox_api.resolve_user(self.username.value)
        except Exception as e:  # Roblox didn't answer
            await interaction.followup.send(t("perm.add_failed", error=str(e)[:200]), ephemeral=True)
            return
        if not found:
            await interaction.followup.send(t("perm.add_not_found", name=self.username.value[:40]), ephemeral=True)
            return
        user_id, name = found
        full = False

        def add(users):
            nonlocal full
            full = False
            if all(u["user_id"] != user_id for u in users):
                if len(users) >= access.MAX_MANAGER_USERS:
                    full = True
                else:
                    users.append({"user_id": user_id, "name": name, "permissions": []})
            return users

        self.panel.status = await change_manager_access(add)
        if full:
            await interaction.followup.send(t("perm.add_full", max=access.MAX_MANAGER_USERS), ephemeral=True)
            await self.panel.redraw()
            return
        self.panel.selected = user_id
        await interaction.followup.send(t("perm.added", name=name), ephemeral=True)
        await self.panel.redraw()


class PickUserSelect(discord.ui.Select):
    def __init__(self, view: "ManagerUsersView", users: list):
        options = [discord.SelectOption(label=u["name"] or str(u["user_id"]), value=str(u["user_id"]),
                                        description=f"ID {u['user_id']}", default=u["user_id"] == view.selected)
                   for u in users[:25]]
        super().__init__(placeholder=t("perm.pick_user"), min_values=1, max_values=1, options=options, row=0)
        self.panel = view

    async def callback(self, interaction: discord.Interaction):
        self.panel.selected = int(self.values[0])
        await self.panel.refresh(interaction)


class UserPermissionSelect(discord.ui.Select):
    def __init__(self, view: "ManagerUsersView", current: list):
        super().__init__(placeholder=t("perm.pick_permissions"), min_values=0, max_values=len(access.GAME_PERMISSIONS),
                         options=permission_options(current, access.GAME_PERMISSIONS), row=1)
        self.panel = view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected, picked = self.panel.selected, list(self.values)

        def tick(users):
            for user in users:
                if user["user_id"] == selected:
                    user["permissions"] = picked
            return users

        self.panel.status = await change_manager_access(tick)
        await self.panel.refresh(interaction)


class ManagerUsersView(AdminView):
    """The Roblox players who may open the ⚙️ Manager in the game, and what the one picked may do there."""

    def __init__(self):
        super().__init__()
        self.selected = None
        self.status = None  # None: nothing sent yet in this window; "": sent; text: why not
        self.add.label = t("perm.btn_add")
        self.remove.label = t("perm.btn_remove")
        self.send.label = t("perm.btn_send")
        self._build()

    def _build(self):
        for item in [i for i in self.children if not isinstance(i, discord.ui.Button)]:
            self.remove_item(item)
        users = access.manager_users()
        if users and self.selected not in {u["user_id"] for u in users}:
            self.selected = users[0]["user_id"]
        if not users:
            self.selected = None
        self.remove.disabled = not users
        if users:
            self.add_item(PickUserSelect(self, users))
            current = next((u["permissions"] for u in users if u["user_id"] == self.selected), [])
            self.add_item(UserPermissionSelect(self, current))

    def embed(self) -> discord.Embed:
        embed = discord.Embed(title=t("perm.game_title"), description=t("perm.game_description"), color=_color())
        lines = []
        for user in access.manager_users():
            mark = "👉 " if user["user_id"] == self.selected else ""
            lines.append(f"{mark}**{user['name']}** ({user['user_id']})\n└ {permission_names(user['permissions'])}")
        embed.add_field(name=t("perm.game_field", count=len(lines)), value=whole_lines(lines, 1024) or t("perm.game_none"),
                        inline=False)
        if self.status == "":
            embed.add_field(name=t("perm.sent_field"), value=t("perm.sent_ok"), inline=False)
        elif self.status:
            embed.add_field(name=t("perm.sent_field"), value=t("perm.sent_failed", error=self.status)[:1024], inline=False)
        embed.set_footer(text=t("perm.game_footer"))
        return embed

    async def refresh(self, interaction: discord.Interaction):
        self._build()
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=self.embed(), view=self)
        else:
            await interaction.response.edit_message(embed=self.embed(), view=self)

    async def redraw(self):
        self._build()
        if self.message is not None:
            try:
                await self.message.edit(embed=self.embed(), view=self)
            except (discord.HTTPException, ValueError):
                pass

    @discord.ui.button(label="Add a player", emoji="➕", style=discord.ButtonStyle.success, row=2)
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddManagerUserModal(self))

    @discord.ui.button(label="Remove the player", emoji="🗑️", style=discord.ButtonStyle.danger, row=2)
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        gone = self.selected
        self.status = await change_manager_access(lambda users: [u for u in users if u["user_id"] != gone])
        self.selected = None
        await self.refresh(interaction)

    @discord.ui.button(label="Send to the game", emoji="📤", style=discord.ButtonStyle.secondary, row=2)
    async def send(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.status = await push_manager_access()
        await self.refresh(interaction)


async def send_manager_users(interaction: discord.Interaction):
    view = ManagerUsersView()
    await send_panel(interaction, view, embed=view.embed())
    if await pull_manager_access():  # the owner changed it in the game: shown as the game has it
        await view.redraw()


async def send_manager(interaction: discord.Interaction):
    view = GamePanelManager(interaction.guild)
    await send_panel(interaction, view, embed=view.embed())


class GamePanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.redrawn = False

    async def redraw_all(self):
        if self.redrawn:
            return
        self.redrawn = True
        for guild in self.bot.guilds:
            try:
                await redraw_posted(guild, force=False)
            except Exception as e:  # one server's problem must not stop the others
                log.warning("Could not check the game control panel in %s: %s", guild.id, e)

    async def cog_load(self):
        if self.bot.is_ready():
            self.bot.loop.create_task(self.redraw_all())

    @commands.Cog.listener()
    async def on_ready(self):
        await self.redraw_all()


async def setup(bot):
    bot.add_view(GamePanelView())
    await bot.add_cog(GamePanel(bot))
