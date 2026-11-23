"""Who may use the bot and where.

1. Servers: the bot's settings are shared by all its servers, so the bot works only on the owner's servers
   (bot_settings.home_guild_ids in config.json). A server is added automatically when the bot's owner (the account
   that owns the bot in the Discord Developer Portal, or a member of its team) owns that server or has Administrator
   or Manage Server there (whoever adds a bot to a server needs Manage Server); anywhere else the bot leaves. The bot's
   owner can also add a server ID in /setup -> Servers before inviting the bot (e.g. when a co-admin invites it).
2. Configuration: panels and admin commands are for server administrators (and the server owner) only. Discord lets a
   server give a command to other roles (Server Settings -> Integrations), but the bot still checks the permission
   itself, so such a change can't open the configuration to non-administrators.
3. Game staff: an administrator chooses roles in /setup -> 🛡️ Permissions and ticks for each role what it may do
   (PERMISSIONS: codes, events, eggs, gifts, announcements, the player card, bans). Members with such a role may use
   those game commands, the control panel buttons and the windows they open (can); the bot's configuration stays
   admin-only. Roles chosen before this list existed (staff_role_ids) keep every permission.
4. The game's ⚙️ Manager: the game's owner always; other Roblox players an administrator added in /setup ->
   🛡️ Permissions -> Manager in the game, each with the permissions ticked for them (manager_users). The list goes
   to the game's DataStore (entry ManagerAccess) and the game checks each action again.
"""
import logging
import time

import discord

from utils import config_store
from utils.i18n import t

log = logging.getLogger("access")
OWNER_CACHE_SECONDS = 600
_owners = {"ids": set(), "at": 0.0, "public": None}


def is_admin(interaction) -> bool:
    """Uses the permissions Discord sends with every click first (always up to date, owner included), then the
    bot's own cache. Checking only the cache could refuse a real administrator right after a restart."""
    if interaction.guild is None:
        return False
    permissions = getattr(interaction, "permissions", None)
    if permissions is not None and permissions.administrator:
        return True
    user = interaction.user
    if getattr(interaction.guild, "owner_id", None) == getattr(user, "id", None):
        return True
    guild_permissions = getattr(user, "guild_permissions", None)
    return bool(guild_permissions and guild_permissions.administrator)


GAME_PANEL = "game_panel"

# What a role (Discord) or a player (the game's ⚙️ Manager) may be allowed to do, in the order the panels show them.
# "settings" is only in the game (the Manager's live settings); the bot's own configuration stays admin-only.
PERMISSIONS = ["codes", "events", "eggs", "gifts", "announce", "players", "bans"]
GAME_PERMISSIONS = [p for p in PERMISSIONS if p != "players"] + ["settings"]  # the Manager shows players to all
PERMISSION_EMOJI = {"codes": "📜", "events": "⚡", "eggs": "🥚", "gifts": "🎁", "announce": "📢", "players": "👤",
                    "bans": "🔨", "settings": "⚙️"}
# The slash commands a permission opens (the others stay admin-only)
# (/codes, /events and /eggs only list things and stay open to everyone, as before)
COMMAND_PERMISSIONS = {"code-add": "codes", "code-remove": "codes", "give": "gifts", "announce-game": "announce",
                       "event-start": "events", "event-stop": "events", "egg-create": "eggs", "egg-edit": "eggs",
                       "egg-remove": "eggs", "roblox-ban": "bans", "roblox-unban": "bans", "roblox-ban-check": "players"}
MANAGER = "game_manager"  # config.json: {"users": [{"user_id", "name", "permissions"}]}
MAX_MANAGER_USERS = 25


def _clean_permissions(values, allowed=PERMISSIONS) -> list:
    picked = {str(v) for v in values} if isinstance(values, (list, tuple, set)) else set()
    return [p for p in allowed if p in picked]


def role_permissions(guild_id: int) -> dict:
    """{role_id: [permission, ...]} chosen in /setup -> 🛡️ Permissions. Roles chosen before the permissions existed
    (staff_role_ids) keep every permission."""
    try:
        section = config_store.guild_section(guild_id, GAME_PANEL)
    except config_store.ConfigError:
        return {}
    result = {}
    old = section.get("staff_role_ids") or []
    for value in old if isinstance(old, list) else []:
        if str(value).isdigit():
            result[int(value)] = list(PERMISSIONS)
    raw = section.get("role_permissions") or {}
    for key, values in (raw.items() if isinstance(raw, dict) else []):
        if str(key).isdigit():
            result[int(key)] = _clean_permissions(values)
    # the server's own ID is @everyone: never a staff role, even if saved by hand
    result.pop(int(guild_id), None)
    return result


def set_role_permissions(guild_id: int, permissions: dict) -> dict:
    """Saves {role_id: [permission, ...]}; the old staff_role_ids list is folded into it."""
    clean = {str(int(k)): _clean_permissions(v) for k, v in permissions.items() if int(k) != int(guild_id)}
    config_store.set_guild_values(guild_id, GAME_PANEL, {"role_permissions": clean, "staff_role_ids": []})
    return role_permissions(guild_id)


def staff_role_ids(guild_id: int) -> list:
    """Roles chosen in /setup -> 🛡️ Permissions (besides administrators), with at least one permission."""
    return sorted(role_id for role_id, perms in role_permissions(guild_id).items() if perms)


def member_permissions(interaction) -> set:
    """Everything this member may do in the game: all for administrators, else what their roles allow."""
    if is_admin(interaction):
        return set(PERMISSIONS)
    if interaction.guild is None:
        return set()
    mine = {role.id for role in getattr(interaction.user, "roles", None) or []}
    result = set()
    for role_id, perms in role_permissions(interaction.guild.id).items():
        if role_id in mine:
            result |= set(perms)
    return result


def can(interaction, permission: str) -> bool:
    """Whether the member may do this game action (an administrator always may)."""
    return permission in member_permissions(interaction)


def is_game_staff(interaction) -> bool:
    """Administrators, and members with a role that has at least one permission in /setup -> 🛡️ Permissions. They see
    the game control panel; each action checks its own permission (can). Never the bot's configuration."""
    return bool(member_permissions(interaction))


def manager_users() -> list:
    """Roblox players who may open the game's ⚙️ Manager besides its owner: [{"user_id", "name", "permissions"}]."""
    try:
        raw = config_store.get(MANAGER).get("users") or []
    except config_store.ConfigError:
        return []
    result = []
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, dict) and str(entry.get("user_id", "")).isdigit():
            result.append({"user_id": int(entry["user_id"]), "name": str(entry.get("name") or "")[:40],
                           "permissions": _clean_permissions(entry.get("permissions"), GAME_PERMISSIONS)})
    return result[:MAX_MANAGER_USERS]


def manager_updated_at() -> int:
    """When the list was last changed here (seconds); the game's owner may also change it in the game's 🛡️ tab."""
    try:
        value = config_store.get(MANAGER).get("updated_at")
    except config_store.ConfigError:
        return 0
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def set_manager_users(users: list, updated_at: int = None) -> list:
    clean, seen = [], set()
    for entry in users:
        user_id = int(entry["user_id"])
        if user_id in seen:
            continue
        seen.add(user_id)
        clean.append({"user_id": user_id, "name": str(entry.get("name") or "")[:40],
                      "permissions": _clean_permissions(entry.get("permissions"), GAME_PERMISSIONS)})
    # always later than the last change (the game's clock may run ahead of this computer's: the newer list must win)
    stamp = max(int(time.time()), manager_updated_at() + 1) if updated_at is None else int(updated_at)
    config_store.set_values([(MANAGER, "users", clean[:MAX_MANAGER_USERS]), (MANAGER, "updated_at", stamp)])
    return manager_users()


def manager_access_entry() -> dict:
    """What the game reads (DataStore entry ManagerAccess): {"users": {"<user id>": {"name", "permissions": [...]}}}.
    updated_at tells the bot and the game which side changed the list last."""
    return {"version": 1, "updated_at": manager_updated_at(),
            "users": {str(u["user_id"]): {"name": u["name"], "permissions": u["permissions"]} for u in manager_users()}}


def adopt_manager_entry(entry, force: bool = False) -> bool:
    """Takes the list as the game saved it (the owner changed it in the game's 🛡️ tab) when it is not older than the
    one here (force: always). Returns True when it was taken."""
    if not isinstance(entry, dict) or not isinstance(entry.get("users"), dict):
        return False
    stamp = entry.get("updated_at")
    stamp = int(stamp) if isinstance(stamp, (int, float)) and not isinstance(stamp, bool) else 0
    if stamp < manager_updated_at() and not force:
        return False  # changed here later (and not sent yet): this list goes to the game on the next send
    users = []
    for user_id, value in entry["users"].items():
        if str(user_id).isdigit() and isinstance(value, dict):
            permissions = value.get("permissions")
            users.append({"user_id": int(user_id), "name": value.get("name") or "",
                          "permissions": permissions if isinstance(permissions, list) else []})
    users.sort(key=lambda u: str(u["name"]).lower())
    set_manager_users(users, updated_at=stamp)
    return True


def has_permissions(interaction, required: discord.Permissions) -> bool:
    """Whether the member has every permission in `required` in this channel (administrators always do)."""
    if interaction.guild is None:
        return False
    if is_admin(interaction):
        return True
    permissions = getattr(interaction, "permissions", None)
    return bool(permissions is not None and (permissions.value & required.value) == required.value)


# ---------- The owner's servers ----------

def home_guild_ids() -> list:
    """The servers the bot works on. None-like values and garbage are ignored."""
    try:
        raw = config_store.get("bot_settings").get("home_guild_ids")
    except config_store.ConfigError:
        return []
    if not isinstance(raw, list):
        return []
    result = []
    for value in raw:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0 and number not in result:
            result.append(number)
    return result


def home_list_exists() -> bool:
    """False until the list was written for the first time (a bot updated from an older version)."""
    try:
        return isinstance(config_store.get("bot_settings").get("home_guild_ids"), list)
    except config_store.ConfigError:
        return False


def is_home_guild(guild_id) -> bool:
    return bool(guild_id) and int(guild_id) in home_guild_ids()


def set_home_guilds(ids: list) -> list:
    clean = []
    for value in ids:
        if int(value) not in clean:
            clean.append(int(value))
    config_store.set_values([("bot_settings", "home_guild_ids", clean)])
    return clean


def add_home_guild(guild_id: int) -> list:
    ids = home_guild_ids()
    if int(guild_id) not in ids:
        ids.append(int(guild_id))
        return set_home_guilds(ids)
    return ids


def remove_home_guild(guild_id: int) -> list:
    return set_home_guilds([g for g in home_guild_ids() if g != int(guild_id)])


async def bot_owner_ids(bot, refresh: bool = False) -> set:
    """IDs of the bot's owner (or its team's members) from the Developer Portal, cached for 10 minutes."""
    if refresh or not _owners["ids"] or time.monotonic() - _owners["at"] > OWNER_CACHE_SECONDS:
        info = await bot.application_info()
        ids = set()
        if info.team:
            ids |= {member.id for member in info.team.members}
        if info.owner:
            ids.add(info.owner.id)
        _owners.update(ids=ids, at=time.monotonic(), public=bool(info.bot_public))
    return set(_owners["ids"])


async def is_bot_owner(bot, user_id: int) -> bool:
    try:
        return int(user_id) in await bot_owner_ids(bot)
    except discord.HTTPException:
        return False


async def bot_is_public(bot):
    """True when "Public Bot" is on in the Developer Portal (anyone can add the bot), None when unknown."""
    try:
        await bot_owner_ids(bot)
    except discord.HTTPException:
        return None
    return _owners["public"]


async def owner_trusts(bot, guild: discord.Guild, membership_enough: bool = False):
    """True when the bot's owner owns this server or has Administrator / Manage Server there (with membership_enough:
    when they are a member at all), False when not, None when it can't be checked right now (Discord didn't answer)."""
    try:
        owners = await bot_owner_ids(bot)
    except discord.HTTPException:
        return None
    if guild.owner_id in owners:
        return True
    for owner_id in owners:
        member = guild.get_member(owner_id)
        if member is None:
            try:
                member = await guild.fetch_member(owner_id)
            except discord.NotFound:
                continue
            except discord.HTTPException:
                return None
        perms = member.guild_permissions
        if membership_enough or perms.administrator or perms.manage_guild:
            return True
    return False


async def check_guild(bot, guild: discord.Guild, joined: bool = False) -> str:
    """Decides what to do with a server the bot is on: "home" (it works there), "added" (just added to the owner's
    servers), "left" (a stranger's server: the bot left it) or "unknown" (couldn't check: the bot stays but ignores it)."""
    if is_home_guild(guild.id):
        return "home"
    trusted = await owner_trusts(bot, guild)
    if trusted:
        add_home_guild(guild.id)
        log.warning("Server %s (%s) was added to the bot's servers: the bot's owner administers it.", guild.name, guild.id)
        return "added"
    if trusted is None:
        log.warning("Could not check whether server %s (%s) belongs to the bot's owner; the bot ignores it for now.",
                    guild.name, guild.id)
        return "unknown"
    log.warning("Server %s (%s) doesn't belong to the bot's owner: the bot leaves it. If it is yours, add it in "
                "/setup -> Servers or make the bot's owner an administrator there.", guild.name, guild.id)
    try:
        if joined:
            await _tell_stranger(guild)
        await guild.leave()
    except discord.HTTPException as e:
        log.error("Could not leave server %s (%s): %s", guild.name, guild.id, e)
        return "unknown"
    return "left"


async def _tell_stranger(guild: discord.Guild) -> None:
    channel = guild.system_channel
    if channel is None or not channel.permissions_for(guild.me).send_messages:
        return
    try:
        await channel.send(t("access.private_bot"))
    except discord.HTTPException:
        pass


async def sync_guilds(bot) -> dict:
    """At start: an older bot without the list trusts every server it is already on (they were all trusted before),
    then every server is checked like a new one. Returns {guild_id: decision}."""
    if not home_list_exists():
        # Before this version every server was trusted: keep each one where the bot's owner is a member (or where it
        # can't be checked now), so an update never cuts an owner off their own community server
        keep = []
        for guild in list(bot.guilds):
            if await owner_trusts(bot, guild, membership_enough=True) is not False:
                keep.append(guild.id)
        set_home_guilds(keep)
        log.warning("The bot now works only on its owner's servers: %s",
                    ", ".join(f"{g.name} ({g.id})" for g in bot.guilds if g.id in keep) or "none yet")
    return {guild.id: await check_guild(bot, guild) for guild in list(bot.guilds)}
