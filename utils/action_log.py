"""The server's log channel: what admins changed in the game (bans, codes, eggs, events, gifts, announcements).
Changes from the game's ⚙️ Manager are written by cogs/game_requests.py, changes from Discord by discord_action()."""
import logging

import discord

from utils import config_store
from utils.i18n import t

log = logging.getLogger("action_log")


async def send(guild: discord.Guild, text: str) -> None:
    """Writes one line to the server's log channel (if one is set). A missing channel or permission is skipped."""
    if guild is None:
        return
    cfg = config_store.guild_section(guild.id, "moderation")
    channel = guild.get_channel(cfg.get("log_channel_id", 0) or 0)
    if channel:
        try:
            await channel.send(text[:1900], allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass


# The kinds of change, the same names as the Manager's requests (cogs/game_requests.py) plus egg_edit from Discord
KINDS = ("code_add", "code_remove", "event_start", "event_stop", "egg_create", "egg_edit", "egg_move", "egg_remove",
         "gift", "announce", "find_player", "ban", "unban")


def kind_label(kind: str) -> str:
    """The kind of change in the server's language ("New egg"); an unknown one stays as it came."""
    kind = str(kind)[:20]
    return t(f"actionlog.kind.{kind}") if kind in KINDS else kind


def result_text(result) -> str:
    """The answer the admin got (a text or an embed) as one text."""
    if isinstance(result, discord.Embed):
        parts = [result.title or "", result.description or ""]
        parts += [f"**{field.name}:** {field.value}" for field in result.fields]
        result = "\n".join(p for p in parts if p)
    return str(result or "").strip()


async def discord_action(interaction: discord.Interaction, kind: str, result) -> None:
    """Writes a change to the game made on Discord to the log channel, like the requests from the game's Manager.
    kind: the same names as the Manager's requests (code_add, egg_create, gift...). result: what the admin got.
    Never raises: the change is already done, a log that fails must not look like a failed change."""
    try:
        await send(interaction.guild, t("actionlog.discord", admin=interaction.user.mention, kind=kind_label(kind),
                                        text=result_text(result)[:1500]))
    except Exception as e:
        log.warning("Could not write %s to the log channel: %s", kind, e)
