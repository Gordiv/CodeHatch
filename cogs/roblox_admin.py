"""Game moderation and the game's leaderboard from Discord, straight through Roblox Open Cloud (no in-game script needed).
The player card (/setup-roblox -> Player card) puts one player's profile, ban and gifts on one screen."""
import calendar
import json
import logging
import re
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils import action_log, cloud_sync, config_store, database, open_cloud, roblox_api
from utils.i18n import L, t
from utils.ui import CloseView, Panel, StaffView, defer_for, send_panel, show_in_place, staff_only

try:  # gifts on the player card; bans and the leaderboard must work even if this module is broken
    from cogs import live_game
except Exception as e:
    live_game = None
    logging.getLogger("roblox_admin").error("cogs/live_game.py could not be loaded: %s", e)

BAN_DURATIONS = {"1h": 3600, "24h": 86400, "3d": 3 * 86400, "7d": 7 * 86400, "30d": 30 * 86400, "permanent": 0}
LEADERBOARD_CACHE_SECONDS = 60
MEDALS = ["🥇", "🥈", "🥉"]
NEW_ACCOUNT_DAYS = 7
CARD_GIFTS = 3


def _color() -> int:
    return config_store.embed_color()


def _seconds(duration: str) -> int:
    match = re.fullmatch(r"(\d+)(?:\.\d+)?s", duration or "")
    return int(match.group(1)) if match else 0


def duration_text(seconds: int) -> str:
    """A ban length without a start time: days, hours or minutes (never "0 h")."""
    if seconds >= 86400:
        return f"{seconds // 86400} d {seconds % 86400 // 3600} h".replace(" 0 h", "")
    if seconds >= 3600:
        return f"{seconds // 3600} h {seconds % 3600 // 60} min".replace(" 0 min", "")
    return f"{max(1, seconds // 60)} min"


def entry_user_id(entry_id: str):
    """OrderedDataStore keys are usually the UserId ('12345', also a short one like '1') or contain it
    ('Player_12345': there at least 3 digits, so 'Slot_2' is not taken for an account)."""
    text = (entry_id or "").strip()
    digits = [text] if text.isascii() and text.isdigit() else re.findall(r"[0-9]{3,}", text)
    user_id = int(digits[-1]) if digits and len(digits[-1]) <= 19 else 0
    return user_id if 0 < user_id < 2 ** 63 else None  # a bigger number would make Roblox refuse every name


async def with_names(entries: list) -> list:
    """[(username or the key, value)]: the leaderboard's keys with the Roblox usernames they stand for."""
    names = await roblox_api.usernames([uid for uid in (entry_user_id(e) for e, _ in entries) if uid])
    return [(names.get(entry_user_id(e)) or e, v) for e, v in entries]


def format_value(value) -> str:
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return str(value)


async def connect_leaderboard(bot, datastore: str, label: str, scope: str) -> str:
    """Saves the leaderboard settings, tries a first read and returns the message for the admin."""
    datastore, label, scope = datastore.strip(), label.strip(), (scope.strip() or "global")
    config_store.set_values([("leaderboard", "datastore", datastore), ("leaderboard", "label", label),
                             ("leaderboard", "scope", scope)])
    cog = bot.get_cog("RobloxAdmin")
    if cog:
        cog.cache.clear()
    try:
        entries = await open_cloud.top_entries(datastore, scope, 3)
    except open_cloud.OpenCloudError as e:
        return t("board.saved_error", error=e)
    if not entries:
        return t("board.saved_empty", datastore=datastore)
    rows = await with_names(entries)  # names, as /leaderboard shows them
    return t("board.saved_ok", sample=", ".join(f"{discord.utils.escape_markdown(str(name))} = {format_value(v)}"
                                                 for name, v in rows))


class LeaderboardModal(discord.ui.Modal):
    """/setup-roblox -> Leaderboard"""

    def __init__(self):
        super().__init__(title=t("board.modal_title"))
        cfg = config_store.load().get("leaderboard", {})
        self.datastore = discord.ui.TextInput(label=t("board.modal_datastore"), max_length=50, default=cfg.get("datastore") or None,
                                              placeholder="PlayerCoins")
        self.label = discord.ui.TextInput(label=t("board.modal_label"), max_length=30, required=False,
                                          default=cfg.get("label") or None, placeholder="Coins")
        self.scope = discord.ui.TextInput(label=t("board.modal_scope"), max_length=50, required=False,
                                          default=cfg.get("scope") or "global")
        for item in (self.datastore, self.label, self.scope):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        message = await connect_leaderboard(interaction.client, self.datastore.value, self.label.value, self.scope.value)
        await send_panel(interaction, CloseView(), content=message)


async def log_action(guild: discord.Guild, text: str):
    """Writes a game moderation action to the server's log channel (if one is set)."""
    await action_log.send(guild, text)


async def ban_player(guild, admin, user_id: int, username: str, seconds: int, reason: str, note: str = "") -> str:
    """Bans the player in every place of the game (also their alt accounts Roblox finds) and writes it to the log.
    Returns the message for the admin. Raises open_cloud.OpenCloudError."""
    if int(user_id) == await roblox_api.game_owner_id(cloud_sync.universe_id()):
        return t("rban.owner_protected", username=username)  # a role with "bans" must not lock the owner out
    private = f"{note} | by {admin} ({admin.id}) via Discord".strip(" |")
    await open_cloud.set_ban(user_id, True, seconds, reason, private)
    until = t("rban.permanent") if not seconds else f"<t:{int(time.time()) + seconds}:f>"
    await log_action(guild, t("rban.log_ban", username=username, user_id=user_id, until=until, reason=reason,
                              admin=admin.mention))
    return t("rban.banned", username=username, until=until, reason=reason)


async def unban_player(guild, admin, user_id: int, username: str) -> str:
    """Lifts the ban and writes it to the log. Returns the message for the admin. Raises open_cloud.OpenCloudError."""
    await open_cloud.set_ban(user_id, False)
    await log_action(guild, t("rban.log_unban", username=username, user_id=user_id, admin=admin.mention))
    return t("rban.unbanned", username=username)


def utc_timestamp(text) -> int:
    """A Roblox time ("2026-10-01T10:00:00.3Z", any number of fraction digits) as a timestamp, 0 if unknown.
    Only the part up to the seconds is read: Python 3.10 can't read every fraction Roblox sends."""
    try:
        return calendar.timegm(time.strptime(str(text or "")[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return 0


def ban_until(ban: dict) -> str:
    """When an active ban ends, from Roblox's start time and duration."""
    seconds = _seconds(ban.get("duration", ""))
    started = utc_timestamp(ban.get("startTime"))
    return t("rban.permanent") if not seconds else (f"<t:{started + seconds}:f>" if started else duration_text(seconds))


class BanConfirmView(Panel):
    """A ban is sent only after the admin saw exactly which account it hits (a typo would ban someone else and,
    with alt accounts, more of their accounts)."""

    def __init__(self, cog, admin, user_id: int, username: str, seconds: int, reason: str, note: str):
        super().__init__(timeout=180)
        self.cog, self.admin = cog, admin
        self.user_id, self.username, self.seconds, self.reason, self.note = user_id, username, seconds, reason, note
        self.confirm.label = t("rban.btn_confirm")
        self.cancel.label = t("common.cancel")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin.id:
            await interaction.response.send_message(t("errors.not_for_you"), ephemeral=True)
            return False
        return await staff_only(interaction, "bans")  # the role may have been taken away meanwhile

    @discord.ui.button(label="Ban", emoji="🔨", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(view=None)
        try:
            message = await ban_player(interaction.guild, self.admin, self.user_id, self.username, self.seconds,
                                       self.reason, self.note)
        except open_cloud.OpenCloudError as e:
            await interaction.followup.send(t("live.failed", error=e), ephemeral=True)
            return
        await interaction.followup.send(message, ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content=t("rban.cancelled"), embed=None, view=None)


# ---------- Player card (/setup-roblox -> Player card) ----------

def _gift_line(row) -> str:
    try:
        reward = live_game.reward_text(json.loads(row["reward"])).replace("\n", ", ") if live_game else ""
    except (ValueError, KeyError, TypeError, StopIteration):
        reward = ""
    by = f" · 🎮 {discord.utils.escape_markdown(row['author'])}" if row["author"] else ""  # sent from the game's Manager
    return f"<t:{int(row['created_at'] or 0)}:R> — {reward or '?'}{by}"


async def player_card(user_id: int, username: str) -> tuple:
    """(embed, banned) for one player. banned is True/False, or None when the ban couldn't be checked."""
    try:
        profile = await roblox_api.get_user(user_id) or {}
    except roblox_api.RobloxApiError:
        profile = {}
    try:  # a busy thumbnail service must not hide the profile (and the new-account warning)
        avatar = await roblox_api.avatar_url(user_id, "150x150")
    except roblox_api.RobloxApiError:
        avatar = ""
    created = utc_timestamp(profile.get("created"))
    lines = [t("card.description", user_id=user_id, created=f"<t:{created}:D> (<t:{created}:R>)" if created else "?")]
    if created and time.time() - created < NEW_ACCOUNT_DAYS * 86400:
        lines.append(t("card.new_account"))  # a fresh account is often a second account of a banned player
    embed = discord.Embed(title=t("card.title", display=profile.get("displayName") or username, username=username)[:256],
                          url=f"https://www.roblox.com/users/{int(user_id)}/profile", description="\n".join(lines),
                          color=_color())
    if avatar:
        embed.set_thumbnail(url=avatar)
    banned = None
    try:
        ban = await open_cloud.get_ban(user_id)
        banned = bool(ban.get("active"))
        value = t("card.ban_active", until=ban_until(ban), reason=ban.get("displayReason") or "—",
                  note=ban.get("privateReason") or "—") if banned else t("card.ban_none")
    except open_cloud.OpenCloudError as e:
        value = t("card.ban_unknown", error=str(e)[:800])
    embed.add_field(name=t("card.field_ban"), value=value[:1024], inline=False)
    embed.set_footer(text=t("card.footer"))
    rows = await database.get_recent_gifts(user_id, CARD_GIFTS)
    embed.add_field(name=t("card.field_gifts"), value=("\n".join(_gift_line(r) for r in rows) or t("card.gifts_none"))[:1024],
                    inline=False)
    return embed, banned


async def send_card(interaction: discord.Interaction, user_id: int, username: str, replace: bool = False):
    """A new card only this person sees, or (replace) the card in place of the message the click came from."""
    embed, banned = await player_card(user_id, username)
    view = PlayerCardView(user_id, username, banned)
    if replace:
        await show_in_place(interaction, view=view, content=None, embed=embed)
    else:
        await send_panel(interaction, view, embed=embed)


class PlayerLookupModal(discord.ui.Modal):
    """The first step of the player card: a username or a Roblox user ID ("@" in front is fine). card: opened from a
    card ("Another player"), so the answer takes that card's place instead of adding a message."""

    def __init__(self, card: "PlayerCardView" = None):
        super().__init__(title=t("card.lookup_title"))
        self.card = card
        self.replace = card is not None
        self.player = discord.ui.TextInput(label=t("rbx.gift_player"), min_length=1, max_length=25,
                                           placeholder=t("rbx.gift_player_ph"))
        self.add_item(self.player)

    async def on_submit(self, interaction: discord.Interaction):
        if not await staff_only(interaction, "players"):  # the role may have been taken away while the form was open
            return
        if self.replace:
            await defer_for(interaction, self.card)  # a closed card: the answer comes as a new message
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)
        text = self.player.value.strip()
        try:
            found = await roblox_api.find_users(text)
        except roblox_api.RobloxApiError as e:
            await self.answer(interaction, f"❌ {e}")
            return
        if not found:
            await self.answer(interaction, t("card.not_found", player=discord.utils.escape_markdown(text)))
            return
        if len(found) > 1:  # a number that is one account's name and another account's ID: the admin picks
            choice = PlayerChoiceView(found)
            text = t("card.ambiguous", player=discord.utils.escape_markdown(text))
            if self.replace:
                await show_in_place(interaction, view=choice, content=text, embed=None)
            else:
                await send_panel(interaction, choice, content=text)
            return
        await send_card(interaction, found[0][0], found[0][1], replace=self.replace)

    async def answer(self, interaction: discord.Interaction, text: str):
        """A problem: written above the card it came from (which stays), or as a message with ✖️ Close."""
        if self.replace:
            await show_in_place(interaction, content=text)
        else:
            await send_panel(interaction, CloseView(), content=text)


class PlayerChoiceButton(discord.ui.Button):
    def __init__(self, user_id: int, username: str, how: str):
        super().__init__(label=t(f"card.by_{how}", username=username, user_id=user_id)[:80],
                         style=discord.ButtonStyle.primary)
        self.user_id, self.username = user_id, username

    async def callback(self, interaction: discord.Interaction):
        self.view.stop()
        await interaction.response.defer()
        await send_card(interaction, self.user_id, self.username, replace=True)  # the card replaces the choice


class PlayerChoiceView(StaffView):
    """Two accounts match the typed number: one by name, one by user ID."""

    permission = "players"

    def __init__(self, found: list):
        super().__init__()
        for user_id, username, how in found:
            self.add_item(PlayerChoiceButton(user_id, username, how))


class BanModal(discord.ui.Modal):
    """A ban from the player card: the admin already sees whose card it is, so no second confirmation."""

    def __init__(self, card: "PlayerCardView"):
        super().__init__(title=t("card.ban_modal_title", username=card.username)[:45])
        self.card = card
        self.duration = discord.ui.Select(options=[discord.SelectOption(label=t(f"duration.choice.{key}")[:100], value=key)
                                                   for key in BAN_DURATIONS], placeholder=t("card.ban_duration_ph"))
        self.reason = discord.ui.TextInput(label=t("rban.confirm_reason"), style=discord.TextStyle.paragraph, max_length=300,
                                           placeholder=t("card.ban_reason_ph"))
        self.note = discord.ui.TextInput(label=t("card.ban_note"), max_length=300, required=False)
        self.add_item(discord.ui.Label(text=t("rban.confirm_duration"), component=self.duration))
        self.add_item(self.reason)
        self.add_item(self.note)

    async def on_submit(self, interaction: discord.Interaction):
        if not await staff_only(interaction, "bans"):  # the role may have been taken away while the form was open
            return
        if not self.duration.values or not self.reason.value.strip():
            await interaction.response.send_message(t("card.err_ban_fields"), ephemeral=True)
            return
        await defer_for(interaction, self.card)  # the card was closed meanwhile: the ban still goes, the answer is new
        try:
            message = await ban_player(interaction.guild, interaction.user, self.card.user_id, self.card.username,
                                       BAN_DURATIONS[self.duration.values[0]], self.reason.value.strip(), self.note.value.strip())
        except open_cloud.OpenCloudError as e:
            await show_in_place(interaction, content=t("live.failed", error=e))  # above the card, which stays
            return
        await self.card.redraw(interaction, note=message)


class PlayerCardView(StaffView):
    """One player on one screen: ban or unban (whichever fits now), a gift, refresh and another player."""

    permission = "players"

    def __init__(self, user_id: int, username: str, banned):
        super().__init__()
        self.user_id, self.username, self.banned = user_id, username, banned
        self.ban.label = t("rban.btn_confirm")
        self.unban.label = t("card.btn_unban")
        self.gift.label = t("rbx.btn_gift")
        self.refresh.label = t("setup.btn_refresh")
        self.other.label = t("card.btn_other")
        if banned is True:  # unknown (no permission yet): both, the click explains the error
            self.remove_item(self.ban)
        if banned is False:
            self.remove_item(self.unban)
        if live_game is None:
            self.remove_item(self.gift)

    async def redraw(self, interaction: discord.Interaction, note: str = None):
        """Reads the player again and replaces the card (after a ban, an unban or on Refresh). note: what just
        happened, written above the card (one message instead of a card plus an answer under it)."""
        embed, banned = await player_card(self.user_id, self.username)
        view = PlayerCardView(self.user_id, self.username, banned)
        self.stop()
        await show_in_place(interaction, view=view, content=note, embed=embed)  # binds the new card after the edit

    @discord.ui.button(label="Ban", emoji="🔨", style=discord.ButtonStyle.danger, row=0)
    async def ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await staff_only(interaction, "bans"):
            return
        self.hold_for_form()
        await interaction.response.send_modal(BanModal(self))

    @discord.ui.button(label="Unban", emoji="✅", style=discord.ButtonStyle.secondary, row=0)
    async def unban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await staff_only(interaction, "bans"):
            return
        # asks first, on the card itself: a slip must not lift a ban. The card stops (the question takes its place)
        # and is drawn again after the answer, so its timer can't remove the question
        question = UnbanConfirmView(self)
        self.stop()
        await interaction.response.edit_message(view=question)

    @discord.ui.button(label="Send a gift", emoji="🎁", style=discord.ButtonStyle.success, row=1)
    async def gift(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await staff_only(interaction, "gifts"):
            return
        from cogs.setup_roblox import GiftModal  # setup_roblox opens this card: imported on click, not at start
        await interaction.response.send_modal(GiftModal(target=(self.user_id, self.username)))

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary, row=2)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()  # a second click on this card is not taken while the new one is drawn
        await interaction.response.defer()
        await self.redraw(interaction)

    @discord.ui.button(label="Another player", emoji="🔍", style=discord.ButtonStyle.secondary, row=2)
    async def other(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.hold_for_form()
        await interaction.response.send_modal(PlayerLookupModal(card=self))


class UnbanConfirmView(StaffView):
    """Replaces the card's buttons for a moment: lift the ban, or go back to the card."""

    permission = "bans"
    close_button = False  # Cancel goes back to the card

    def __init__(self, card: PlayerCardView):
        super().__init__()
        self.card = card
        self.message = card.message
        self.yes.label = t("card.btn_unban_yes", username=card.username)[:80]
        self.no.label = t("common.cancel")

    @discord.ui.button(label="Yes, unban", emoji="✅", style=discord.ButtonStyle.danger)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.defer()
        try:
            message = await unban_player(interaction.guild, interaction.user, self.card.user_id, self.card.username)
        except open_cloud.OpenCloudError as e:
            await self.card.redraw(interaction, note=t("live.failed", error=e))
            return
        await self.card.redraw(interaction, note=message)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.defer()
        await self.card.redraw(interaction)


class RobloxAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cache = {}

    async def resolve(self, interaction: discord.Interaction, player: str):
        try:
            user = await roblox_api.resolve_user(player)
        except roblox_api.RobloxApiError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
            return None
        if not user:
            await interaction.followup.send(t("verify.user_not_found", username=player), ephemeral=True)
        return user

    @app_commands.command(name="roblox-ban", description=L("cmd.roblox_ban"))
    @app_commands.guild_only()
    @app_commands.describe(player=L("cmd.roblox_ban.player"), duration=L("cmd.roblox_ban.duration"),
                           reason=L("cmd.roblox_ban.reason"), note=L("cmd.roblox_ban.note"))
    @app_commands.choices(duration=[app_commands.Choice(name=L(f"duration.choice.{k}"), value=k) for k in BAN_DURATIONS])
    async def roblox_ban(self, interaction: discord.Interaction, player: app_commands.Range[str, 3, 20],
                         duration: app_commands.Choice[str], reason: app_commands.Range[str, 1, 300],
                         note: app_commands.Range[str, 0, 300] = ""):
        await interaction.response.defer(ephemeral=True, thinking=True)
        user = await self.resolve(interaction, player)
        if not user:
            return
        user_id, username = user
        seconds = BAN_DURATIONS[duration.value]
        try:
            profile = await roblox_api.get_user(user_id) or {}
            avatar = await roblox_api.avatar_url(user_id, "150x150")
        except roblox_api.RobloxApiError:
            profile, avatar = {}, ""
        embed = discord.Embed(title=t("rban.confirm_title"), color=discord.Color.red(),
                              description=t("rban.confirm_description", username=username, user_id=user_id,
                                            display=profile.get("displayName") or username,
                                            created=str(profile.get("created") or "?")[:10]))
        embed.add_field(name=t("rban.confirm_duration"), value=t("rban.permanent") if not seconds else duration_text(seconds),
                        inline=True)
        embed.add_field(name=t("rban.confirm_reason"), value=reason[:1024], inline=True)
        embed.add_field(name=t("rban.confirm_profile"), value=f"https://www.roblox.com/users/{user_id}/profile", inline=False)
        if avatar:
            embed.set_thumbnail(url=avatar)
        view = BanConfirmView(self, interaction.user, user_id, username, seconds, reason, note)
        await send_panel(interaction, view, embed=embed)

    @app_commands.command(name="roblox-unban", description=L("cmd.roblox_unban"))
    @app_commands.guild_only()
    @app_commands.describe(player=L("cmd.roblox_ban.player"))
    async def roblox_unban(self, interaction: discord.Interaction, player: app_commands.Range[str, 3, 20]):
        await interaction.response.defer(ephemeral=True, thinking=True)
        user = await self.resolve(interaction, player)
        if not user:
            return
        user_id, username = user
        try:
            message = await unban_player(interaction.guild, interaction.user, user_id, username)
        except open_cloud.OpenCloudError as e:
            await interaction.followup.send(t("live.failed", error=e), ephemeral=True)
            return
        await interaction.followup.send(message, ephemeral=True)

    @app_commands.command(name="roblox-ban-check", description=L("cmd.roblox_ban_check"))
    @app_commands.guild_only()
    @app_commands.describe(player=L("cmd.roblox_ban.player"))
    async def roblox_ban_check(self, interaction: discord.Interaction, player: app_commands.Range[str, 3, 20]):
        await interaction.response.defer(ephemeral=True, thinking=True)
        user = await self.resolve(interaction, player)
        if not user:
            return
        user_id, username = user
        try:
            ban = await open_cloud.get_ban(user_id)
        except open_cloud.OpenCloudError as e:
            await interaction.followup.send(t("live.failed", error=e), ephemeral=True)
            return
        if not ban.get("active"):
            await interaction.followup.send(t("rban.not_banned", username=username), ephemeral=True)
            return
        await interaction.followup.send(t("rban.status", username=username, until=ban_until(ban),
                                          reason=ban.get("displayReason") or "—", note=ban.get("privateReason") or "—"),
                                        ephemeral=True)

    # ---------- leaderboard ----------
    @app_commands.command(name="leaderboard", description=L("cmd.leaderboard"))
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction):
        cfg = config_store.get("leaderboard")
        if not cfg.get("datastore"):
            await interaction.response.send_message(t("board.not_configured"), ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        key = (cfg["datastore"], cfg.get("scope") or "global")
        cached = self.cache.get(key)
        if cached and time.time() - cached[0] < LEADERBOARD_CACHE_SECONDS:
            rows = cached[1]
        else:
            try:
                entries = await open_cloud.top_entries(cfg["datastore"], cfg.get("scope") or "global", 10)
            except open_cloud.OpenCloudError as e:
                await interaction.followup.send(t("live.failed", error=e))
                return
            rows = await with_names(entries)
            self.cache[key] = (time.time(), rows)
        label = cfg.get("label") or ""
        if not rows:
            description = t("board.empty")
        else:
            description = "\n".join(f"{MEDALS[i] if i < 3 else f'`#{i + 1}`'} **{discord.utils.escape_markdown(str(name))}**"
                                    f" — {format_value(value)} {label}" for i, (name, value) in enumerate(rows))
        embed = discord.Embed(title=t("board.title", label=label).strip(), description=description, color=_color())
        embed.set_footer(text=t("board.footer"))
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="leaderboard-setup", description=L("cmd.leaderboard_setup"))
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.describe(datastore=L("cmd.leaderboard_setup.datastore"), label=L("cmd.leaderboard_setup.label"),
                           scope=L("cmd.leaderboard_setup.scope"))
    async def leaderboard_setup(self, interaction: discord.Interaction, datastore: app_commands.Range[str, 1, 50],
                                label: app_commands.Range[str, 0, 30] = "", scope: app_commands.Range[str, 1, 50] = "global"):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.followup.send(await connect_leaderboard(self.bot, datastore, label, scope), ephemeral=True)


async def setup(bot):
    await bot.add_cog(RobloxAdmin(bot))
