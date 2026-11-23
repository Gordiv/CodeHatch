import asyncio
import hashlib
import json
import logging
import os
import sys
import time

# Force UTF-8 and line buffering in the Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    # A click into the bot's console window turns on "Select" (QuickEdit) mode, which pauses every print and with it
    # the whole bot until Esc is pressed: switched off for this window
    try:
        import ctypes
        _kernel32 = ctypes.windll.kernel32
        _console_in = _kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        _mode = ctypes.c_uint32()
        if _kernel32.GetConsoleMode(_console_in, ctypes.byref(_mode)):
            # off: ENABLE_QUICK_EDIT_MODE (0x40); ENABLE_EXTENDED_FLAGS (0x80) makes the change count
            _kernel32.SetConsoleMode(_console_in, (_mode.value & ~0x0040) | 0x0080)
            # the mode belongs to the window, not to Python: back on when the bot stops, so an error shown by
            # start.bat afterwards can still be selected and copied
            import atexit
            atexit.register(_kernel32.SetConsoleMode, _console_in, _mode.value | 0x0080)
    except Exception:  # noqa: BLE001 - no console (a host, a service): nothing to switch off
        pass

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import dotenv_values, load_dotenv

from utils import access, config_store, database, docs_site, env_store, i18n, instance_lock, logs, net, error_reports
from utils.i18n import t
from utils.version import VERSION

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
# An empty file with this name restarts a bot started with start.bat/start.sh (e.g. written by a restart script)
RESTART_REQUEST = os.path.join(DATA_DIR, "restart.request")
STATUS_FILE = os.path.join(DATA_DIR, "bot_status.json")
COMMANDS_HASH_FILE = "commands_hash.json"
VERSION_FILE = "bot_version.json"  # the version that ran last time: after an update the owner is told what changed
# The bot's modules. Only these are loaded: an update is copied over the old folder, so a file an older version had
# and the new one dropped may still be there, and it must not start.
COGS = ("cloud_sync", "game_codes", "game_panel", "game_requests", "help", "live_game", "roblox_admin", "setup",
        "setup_guide", "setup_roblox", "tutorial")
# View Channels, Send Messages, Embed Links, Read Message History: the four the docs and /tutorial name and check
INVITE_PERMISSIONS = 84992
# Exit codes read by start.bat / start.sh
EXIT_ERROR = 1
RESTART_EXIT_CODE = 42  # the launcher starts the bot again (after a restart request, see RESTART_REQUEST)

log = logging.getLogger("bot")


def say(key: str, **kwargs) -> None:
    """A start-up message in the bot's language; in all three when config.json can't be read (language unknown)."""
    if config_store.last_error():
        for lang in i18n.LANGUAGES:
            print(t(key, lang=lang, **kwargs))
    else:
        print(t(key, **kwargs))


def load_env() -> None:
    """.env first. A real value in .env wins over the same variable set in the system (e.g. left over from another
    program), with a warning; an example value in .env never hides a real one from the system."""
    path = os.path.join(ROOT, ".env")
    for line, start in env_store.broken_lines(path):
        say("startup.env_broken_line", line=line, start=start)
    values = dotenv_values(path) if os.path.exists(path) else {}
    for name, value in values.items():
        if value is None:
            continue
        current = os.environ.get(name)
        if current is not None and current != value and not env_store.is_placeholder(value):
            print(t("startup.env_override", name=name))
        if current is None or not env_store.is_placeholder(value):
            os.environ[name] = value
    load_dotenv(path, override=False)


intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned,  # no text commands: slash commands only
    intents=intents,
    help_command=None,
    # Every command is a server command: none works in direct messages or as a "user app" (K2)
    allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=False),
    allowed_installs=app_commands.AppInstallationType(guild=True, user=False),
)
bot.restart_requested = False
bot.commands_synced = False
bot.failed_extensions = []
bot.restart_watcher = None
bot.ready_once = False
error_reports.install(bot)


async def watch_restart_requests():
    while not bot.is_closed():
        await asyncio.sleep(3)
        if not os.path.exists(RESTART_REQUEST):
            continue
        try:
            os.remove(RESTART_REQUEST)
        except OSError:
            pass
        if os.getenv("BOT_LAUNCHER") in ("start.bat", "start.sh"):
            print("🔄 Restart requested - restarting the bot...")
            bot.restart_requested = True
            await bot.close()
            return
        print("⚠️ Restart requested, but the bot was not started with start.bat/start.sh. Restart it manually.")


def write_status(commands: int):
    """Start report in data/bot_status.json (e.g. for a restart script): version, modules that failed to load, synced
    commands."""
    status = {"started_at": int(time.time()), "version": VERSION, "pid": os.getpid(),
              "launcher": os.getenv("BOT_LAUNCHER") or "", "guilds": len(bot.guilds), "commands": commands,
              "failed_extensions": bot.failed_extensions}
    try:
        config_store.write_json(os.path.basename(STATUS_FILE), status)
    except OSError as e:
        print(f"⚠️ Could not write {STATUS_FILE}: {e}")


async def commands_hash() -> str:
    """Fingerprint of every command as Discord gets it (names, options, translations, permissions)."""
    translator = bot.tree.translator
    payloads = []
    for command in sorted(bot.tree.get_commands(), key=lambda c: c.name):
        payloads.append(await command.get_translated_payload(bot.tree, translator) if translator else command.to_dict(bot.tree))
    return hashlib.sha256(json.dumps(payloads, sort_keys=True, default=str).encode("utf-8")).hexdigest()


async def notify_owner(text: str) -> None:
    """A message for the owner on the log channel (/setup -> Channels), e.g. when the commands could not be synced."""
    channel_id = config_store.get("moderation").get("log_channel_id", 0)
    channel = bot.get_channel(channel_id) if channel_id else None
    if channel:
        try:
            await channel.send(text[:1900], allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass


async def sync_commands() -> None:
    """Sends the slash commands to Discord, but only when they changed since the last sync (Discord limits how often
    commands may be synced; a start without changes needs nothing)."""
    digest = await commands_hash()
    saved = config_store.read_json(COMMANDS_HASH_FILE, {})
    if saved.get("hash") == digest and saved.get("application_id") == bot.application_id:
        bot.commands_synced = True
        print(f"✅ Slash commands are up to date ({len(bot.tree.get_commands())}).")
        write_status(len(bot.tree.get_commands()))
        return
    print("⏳ Syncing slash commands...")
    try:
        # Global commands only. Server copies from older versions are removed, otherwise every command shows up twice.
        for guild in bot.guilds:
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)
        synced_global = await bot.tree.sync()
    except Exception as e:
        print(f"❌ Slash command sync failed: {e}")
        write_status(-1)
        await notify_owner(t("startup.sync_failed", error=error_reports.sanitize(e)))
        return
    bot.commands_synced = True
    config_store.write_json(COMMANDS_HASH_FILE, {"hash": digest, "application_id": bot.application_id,
                                                 "at": int(time.time())})
    print(f"✅ Synced {len(synced_global)} commands globally!")
    write_status(len(synced_global))


@bot.event
async def on_ready():
    print("==================================================")
    print(f"📦 CodeHatch {VERSION}")
    print(f"🤖 Logged in as: {bot.user} (ID: {bot.user.id})")
    print("🎮 The bot is ONLINE!")
    print(f"🌐 Connected servers ({len(bot.guilds)}): {[g.name for g in bot.guilds]}")
    print(f"🗣️ Bot language: {i18n.LANGUAGES[i18n.language()]}")
    print("==================================================")

    status_text = config_store.get("bot_settings").get("status_message", "CodeHatch | /help")
    await bot.change_presence(activity=discord.Game(name=status_text))
    if bot.restart_watcher is None:
        bot.restart_watcher = asyncio.create_task(watch_restart_requests())

    # on_ready fires again after every reconnect; this part runs once per start
    if bot.ready_once:
        return
    bot.ready_once = True
    previous = version_change()
    if previous:
        say("startup.updated", old=previous, new=VERSION)
        await notify_owner(t("startup.updated", old=previous, new=VERSION))
    decisions = await access.sync_guilds(bot)
    for guild_id, decision in decisions.items():
        if decision == "unknown":
            print(f"⚠️ {t('access.console_unknown', guild=guild_id)}")
    if await access.bot_is_public(bot):
        print(f"⚠️ {t('access.console_public')}")
    asyncio.create_task(database.backup_loop())
    bot.dispatch("bot_started")
    await sync_commands()


@bot.event
async def on_guild_join(guild: discord.Guild):
    decision = await access.check_guild(bot, guild, joined=True)
    if decision in ("home", "added"):
        bot.dispatch("home_guild_join", guild)


async def global_command_check(interaction: discord.Interaction) -> bool:
    """Runs before every slash command: the right place (one of the owner's servers, the bot is a member there) and
    the permission the command needs, checked by the bot itself (not only by Discord's command settings)."""
    if interaction.guild_id is None:
        await error_reports.safe_reply(interaction, t("errors.server_only"))
        return False
    if bot.get_guild(interaction.guild_id) is None:
        # Added only as an app ("Add to my apps"): commands show up, but the bot can't see the server, roles or channels
        invite = (f"https://discord.com/oauth2/authorize?client_id={bot.application_id}"
                  f"&scope=bot+applications.commands&permissions={INVITE_PERMISSIONS}")
        await error_reports.safe_reply(interaction, t("errors.bot_not_in_server", invite=invite))
        return False
    if not access.is_home_guild(interaction.guild_id):
        # Right after the first start of an updated bot the list of the owner's servers is still being made
        await error_reports.safe_reply(interaction, t("errors.not_home_guild" if access.home_list_exists() else "errors.starting"))
        return False
    command = interaction.command
    root = command.root_parent if command is not None and command.root_parent else command
    permission = access.COMMAND_PERMISSIONS.get(getattr(root, "name", ""))
    if permission is not None:  # a game command: the roles an administrator allowed it in /setup -> 🛡️ Permissions
        if not access.can(interaction, permission):
            if getattr(interaction, "type", None) != discord.InteractionType.autocomplete:
                await error_reports.safe_reply(interaction, t("perm.no_access", what=t(f"perm.{permission}")))
            return False
        return True
    required = getattr(root, "default_permissions", None) or getattr(command, "default_permissions", None)
    if required is not None and required.value and not access.has_permissions(interaction, required):
        await error_reports.safe_reply(interaction, t("errors.no_permission"))
        return False
    return True


bot.tree.interaction_check = global_command_check


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await error_reports.safe_reply(interaction, t("errors.no_permission"))
    elif isinstance(error, app_commands.BotMissingPermissions):
        await error_reports.safe_reply(interaction, t("errors.bot_missing", perms=", ".join(error.missing_permissions)))
    elif isinstance(error, app_commands.CommandOnCooldown):
        await error_reports.safe_reply(interaction, t("errors.cooldown", seconds=round(error.retry_after, 1)))
    elif isinstance(error, app_commands.CheckFailure):
        if not interaction.response.is_done():
            await error_reports.safe_reply(interaction, t("errors.check_failed"))
    else:
        command_name = f"/{interaction.command.qualified_name}" if interaction.command else "command"
        await error_reports.handle_interaction_error(bot, interaction, getattr(error, "original", error), command_name,
                                                 unexpected_key="errors.unexpected_command")


async def load_extensions():
    for name in COGS:
        extension_name = f"cogs.{name}"
        try:
            await bot.load_extension(extension_name)
            print(f"📦 Loaded module: {extension_name}")
        except Exception as e:
            bot.failed_extensions.append(f"{extension_name}: {type(e).__name__}: {e}"[:300])
            print(f"❌ Failed to load module {extension_name}: {e}")


def version_change() -> str:
    """The version that ran before this start when it was another one ("" on the first start or without a change).
    Remembers this version for the next start."""
    previous = str(config_store.read_json(VERSION_FILE, {}).get("version") or "")
    if previous != VERSION:
        try:
            config_store.write_json(VERSION_FILE, {"version": VERSION, "at": int(time.time())})
        except OSError as e:
            print(f"⚠️ Could not write {VERSION_FILE}: {e}")
    return previous if previous and previous != VERSION else ""


async def login_with_retry(token: str) -> None:
    """Logs in; without internet it waits and tries again instead of stopping (e.g. a computer that starts the bot
    before the network is up)."""
    delay = 10
    while True:
        try:
            await bot.login(token)
            return
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError, OSError) as e:
            say("startup.no_internet", seconds=delay, error=error_reports.sanitize(e))
            await asyncio.sleep(delay)
            delay = min(delay * 2, 300)


async def main() -> int:
    log_file = logs.setup()
    load_env()
    try:
        config_store.load()
    except config_store.ConfigError as e:
        say("startup.config_broken", error=e, path=config_store.CONFIG_PATH)
        return EXIT_ERROR
    print(f"📝 {t('startup.log_file', path=log_file)}")

    token = env_store.secret("DISCORD_TOKEN")
    if not token:
        say("startup.no_token")
        return EXIT_ERROR

    lock = instance_lock.InstanceLock()
    if not lock.acquire():
        say("startup.already_running")
        return instance_lock.ALREADY_RUNNING_EXIT_CODE
    try:
        return await run(token)
    finally:
        await net.close()
        await database.close_db()
        lock.release()


async def run(token: str) -> int:
    # DOCS.html (the documentation page) follows the installed texts, also after an update
    docs_site.refresh()

    try:
        await database.init_db()
    except Exception as e:
        say("startup.database_error", error=e)
        return EXIT_ERROR
    print("🗄️ SQLite database initialised.")

    async with bot:
        await bot.tree.set_translator(i18n.Translator())
        await load_extensions()
        await login_with_retry(token)
        await bot.connect()
    return 0


def run_main() -> int:
    try:
        return asyncio.run(main())
    except discord.LoginFailure:
        say("startup.bad_token")
    except discord.PrivilegedIntentsRequired:
        say("startup.intents")
    except KeyboardInterrupt:
        return 0
    return EXIT_ERROR


if __name__ == "__main__":
    exit_code = run_main()
    if bot.restart_requested:
        sys.exit(RESTART_EXIT_CODE)
    sys.exit(exit_code)
