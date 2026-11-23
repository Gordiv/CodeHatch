"""Error reports of the bot: an unexpected error in a command, button, form or event is written to the log and posted
on the owner's own bug channel (/setup -> Channels). Nothing leaves the owner's server.

Secrets (the bot token, API keys, webhook addresses) and the user's folder name are removed from every report.
"""
import logging
import os
import platform
import re
import sys
import time
import traceback
from collections import deque

import discord

from utils import config_store
from utils.i18n import t
from utils.version import VERSION

CRASH_COOLDOWN_SECONDS = 600
CRASH_MAX_PER_HOUR = 20

log = logging.getLogger("error_reports")

_SECRET_PATTERNS = [
    re.compile(r"[MNO][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6,7}\.[A-Za-z0-9_-]{27,}"),
    re.compile(r"AIza[A-Za-z0-9_-]{30,}"),
    re.compile(r"https?://(?:[\w-]+\.)?discord(?:app)?\.com/api/(?:v\d+/)?webhooks/\d+/[\w-]+"),
    re.compile(r"_\|WARNING:-DO-NOT-SHARE[^\s\"']+"),
]
WEBHOOK_PATTERN = _SECRET_PATTERNS[2]
_KEY_VALUE = re.compile(r"(?i)\b(token|api[_-]?key|secret|password|authorization)(\s*[=:]\s*)[^\s,;\"']+")
_USER_PATH = re.compile(r"(?i)([A-Z]:[\\/]+Users[\\/]+|/Users/|/home/)[^\\/\s\"']+")
_SECRET_ENV_NAMES = ("DISCORD_TOKEN", "ROBLOX_API_KEY")

_last_sent = {}
_sent_times = deque()


def sanitize(text) -> str:
    text = str(text)
    for name in _SECRET_ENV_NAMES:
        value = os.getenv(name)
        if value and len(value) >= 8:
            text = text.replace(value, "<hidden>")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("<hidden>", text)
    text = _KEY_VALUE.sub(r"\1\2<hidden>", text)
    return _USER_PATH.sub(r"\1<user>", text)


def environment_info(bot, guild: discord.Guild = None) -> dict:
    """Technical details attached to a report (in English, like the log)."""
    try:
        cfg = config_store.load()
    except config_store.ConfigError:
        cfg = {}
    return {
        "Bot version": VERSION,
        "Environment": f"Python {platform.python_version()} • discord.py {discord.__version__} • {platform.system()} {platform.release()}",
        "Server": f"{guild.name} (`{guild.id}`) • members: {guild.member_count}" if guild else "—",
        "Language": (cfg.get("bot_settings") or {}).get("language", "en"),
        "Modules": ", ".join(sorted(c.lower() for c in getattr(bot, "cogs", {}))) or "—",
    }


async def _to_bug_channel(bot, embed: discord.Embed) -> bool:
    try:
        channel_id = config_store.get("ai_support").get("developer_bug_channel_id", 0)
    except config_store.ConfigError:
        return False
    channel = bot.get_channel(channel_id) if channel_id and hasattr(bot, "get_channel") else None
    if not channel:
        return False
    try:
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        return True
    except discord.HTTPException as e:
        log.warning("Could not post a report on the bug channel: %s", e)
        return False


async def report_crash(bot, source: str, error: BaseException, guild: discord.Guild = None) -> None:
    """Writes the error to the log and posts it on the bug channel (the same error at most every 10 minutes, at most
    20 reports an hour)."""
    try:
        tb = sanitize("".join(traceback.format_exception(type(error), error, error.__traceback__)))
        summary = f"{type(error).__name__}: {sanitize(error)}"[:200]
        print(f"[Error in {source}]\n{tb}", file=sys.stderr)

        now = time.time()
        for signature, sent_at in list(_last_sent.items()):  # old entries are not needed any more
            if now - sent_at >= CRASH_COOLDOWN_SECONDS:
                del _last_sent[signature]
        signature = f"{source}|{summary}"
        if signature in _last_sent:
            return
        while _sent_times and now - _sent_times[0] > 3600:
            _sent_times.popleft()
        if len(_sent_times) >= CRASH_MAX_PER_HOUR:
            return
        _last_sent[signature] = now
        _sent_times.append(now)

        embed = discord.Embed(
            title=f"💥 Error: {type(error).__name__}",
            description=f"```py\n{tb[-3700:]}\n```",
            color=discord.Color.red(),
        )
        embed.add_field(name="Source", value=f"`{source}`"[:1024], inline=True)
        for name, value in environment_info(bot, guild).items():
            embed.add_field(name=name, value=str(value)[:1024], inline=name == "Bot version")
        await _to_bug_channel(bot, embed)
    except Exception as e:
        print(f"[Error reports] Failed to post the error report: {e}", file=sys.stderr)


def is_permission_error(error: BaseException) -> bool:
    """The bot itself lacks a Discord permission: something for the server owner to fix, not a bug report."""
    return isinstance(error, discord.Forbidden)


def is_expired_interaction(error: BaseException) -> bool:
    """The reply came too late (Discord forgets an interaction after 3 s / 15 min): nothing to answer any more."""
    return isinstance(error, discord.NotFound) and getattr(error, "code", 0) in (10062, 10008, 10015)


async def safe_reply(interaction: discord.Interaction, text: str) -> None:
    """Answers an interaction in any state; an answer that can't be sent any more is skipped."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except discord.HTTPException:
        pass


async def handle_interaction_error(bot, interaction: discord.Interaction, error: BaseException, source: str,
                                   unexpected_key: str = "errors.unexpected") -> None:
    """Shared answer for errors in commands, buttons, menus and forms."""
    if is_expired_interaction(error):
        log.info("An interaction expired before the answer (%s).", source)
        return
    if is_permission_error(error):
        log.warning("Missing Discord permission in %s: %s", source, error)
        await safe_reply(interaction, t("errors.bot_forbidden"))
        return
    await report_crash(bot, source, error, interaction.guild)
    await safe_reply(interaction, t(unexpected_key))


def install(bot) -> None:
    """Hooks error reporting into buttons, selects, modals and events.

    discord.py has no setting for this, so the default on_error of every View and Modal is replaced (once, for the
    whole program). A View or Modal that defines its own on_error keeps it."""
    async def view_on_error(self, interaction, error, item):
        await handle_interaction_error(bot, interaction, error, f"{type(self).__name__}/{type(item).__name__}")

    async def modal_on_error(self, interaction, error):
        await handle_interaction_error(bot, interaction, error, type(self).__name__)

    discord.ui.View.on_error = view_on_error
    discord.ui.Modal.on_error = modal_on_error

    @bot.event
    async def on_error(event_method, *args, **kwargs):
        error = sys.exc_info()[1]
        if error:
            await report_crash(bot, f"event:{event_method}", error)
