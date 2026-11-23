import logging
import re
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils import action_log, catalog, cloud_sync, config_store, database, i18n, roblox_kit
from utils.i18n import L, t
from utils.ui import CloseView, Panel, close_message, send_panel, show_in_place, staff_only

# Same rules as the in-game script: no spaces or non-ASCII letters (Roblox does not change their case)
CODE_PATTERN = re.compile(r"[A-Z0-9_-]{1,30}")  # the game saves "UserId_CODE": Roblox keys hold at most 50 characters
NONE = "none"
ECONOMY_FILE = "game_economy.json"
MAX_AMOUNT = 1_000_000_000
CODES_PER_PAGE = 10

CODE_VALIDITY = {"24h": 86400, "3d": 3 * 86400, "7d": 7 * 86400, "14d": 14 * 86400, "30d": 30 * 86400, "unlimited": 0}

# key -> (duration in seconds, is temporary)
ITEM_DURATIONS = {
    "permanent": (0, 0),
    "1h": (3600, 1),
    "3h": (3 * 3600, 1),
    "6h": (6 * 3600, 1),
    "12h": (12 * 3600, 1),
    "24h": (86400, 1),
    "3d": (3 * 86400, 1),
    "7d": (7 * 86400, 1),
    "14d": (14 * 86400, 1),
    "30d": (30 * 86400, 1),
}

log = logging.getLogger("game_codes")


class CodeError(Exception):
    """A code that can't be saved; the message is ready for the admin."""


def _chosen(name) -> bool:
    """A name was picked: not empty and not "none" ("Brak" is how older versions stored it), in any letter case."""
    return bool(name and name.strip()) and name.strip().lower() not in (NONE, "brak")


def made_in_game(row) -> str:
    """"🎮 Made in the game's ⚙️ Manager by X" for a code, event or egg the game made itself; "" for one from Discord."""
    if row["origin"] != "game":
        return ""
    return t("codes.made_in_game", name=discord.utils.escape_markdown(row["author"] or "?"))


def is_live(row) -> bool:
    """An active code that hasn't expired yet (the clean-up loop marks expired codes inactive only every 5 minutes)."""
    return bool(row and row["is_active"] and (not row["expires_at"] or row["expires_at"] > time.time()))


def code_params(code: str, validity: str, currency_type: str = NONE, currency_amount: int = 0, exp_amount: int = 0,
                item_reward: str = NONE, item_key: str = "permanent", allow_empty: bool = False) -> dict:
    """Checks a new code the way the game reads it and returns the arguments of save_code. Raises CodeError.
    Used by /code-add and by the form in /setup-roblox -> Codes, so both refuse the same things. allow_empty: a draft
    in the panel may still get its EXP before saving (a saved code without any reward is refused: the game would use
    it up and give nothing); the draft also only warns about currency above the game's limit, saving refuses it."""
    if re.search(r"\s", code.strip()):
        # The game removes spaces when a player types a code, so "SUMMER 24" and "SUMMER24" would be one code
        raise CodeError(t("codes.no_spaces"))
    code_clean = code.strip().upper()
    if not CODE_PATTERN.fullmatch(code_clean):
        raise CodeError(t("codes.invalid_format"))
    if _chosen(currency_type) != (currency_amount > 0):  # a currency without an amount (or the other way) gives nothing
        raise CodeError(t("codes.err_currency_amount"))
    if not allow_empty and not (_chosen(currency_type) or exp_amount > 0 or _chosen(item_reward)):
        raise CodeError(t("codes.err_no_rewards"))
    # The game catalog knows the exact names: a typo would make a code nobody can redeem
    errors = []
    if _chosen(currency_type):
        currency_type, error = catalog.resolve("currencies", currency_type)
        errors.append(error)
    if _chosen(item_reward):
        item_reward, error = catalog.resolve("reward_item", item_reward)
        errors.append(error)
    if any(errors):
        raise CodeError(catalog.error_message(errors))
    if not allow_empty and _chosen(currency_type):  # a code above Settings -> MaxCurrencyPerCode can't be redeemed
        reward = {"currency": {"name": currency_type, "amount": currency_amount}}
        error = roblox_kit.limit_error(roblox_kit.game_scan(), reward)
        if error:
            raise CodeError(error)
    return {"code": code_clean, "validity": validity, "currency_type": currency_type, "currency_amount": currency_amount,
            "exp_amount": exp_amount, "item_reward": item_reward, "item_key": item_key}


def duration_label(label: str) -> str:
    """Translated duration name; codes created by older versions keep their stored text."""
    key = f"duration.choice.{label}"
    return t(key) if i18n.has_key(key, i18n.DEFAULT_LANGUAGE) else label


def describe_code(c) -> str:
    rewards = []
    if c["reward_currency"] and c["currency_amount"] > 0:
        rewards.append(f"{c['currency_amount']:,} {c['reward_currency']}")
    if c["exp_amount"] > 0:
        rewards.append(f"{c['exp_amount']:,} EXP")
    if c["reward_item"]:
        rewards.append(c["reward_item"])
    # A select option can't show a Discord timestamp, so the time is written in UTC and says so
    expiry = t("codes.until", date=time.strftime("%d.%m %H:%M UTC", time.gmtime(c["expires_at"]))) if c["expires_at"] \
        else t("codes.no_limit")
    return f"{', '.join(rewards) or t('codes.no_rewards_short')} • {expiry}"[:100]


def economy() -> dict:
    return config_store.read_json(ECONOMY_FILE, {})


def code_field(c) -> tuple:
    expires_at = c["expires_at"]
    time_str = t("codes.expires_in", time=f"<t:{expires_at}:R>") if expires_at > 0 else t("codes.expires_never")
    rewards = []
    if c["reward_currency"] and c["currency_amount"] > 0:
        rewards.append(f"💰 **{c['currency_amount']:,}** {c['reward_currency']}")
    if c["exp_amount"] > 0:
        rewards.append(f"⭐ **+{c['exp_amount']:,}** EXP")
    if c["reward_item"]:
        dur = f" ({duration_label(c['item_duration_label'])})" if c["is_temporary_item"] else ""
        rewards.append(f"🎁 **{c['reward_item']}**{dur}")
    value = "\n".join(rewards) if rewards else t("codes.free_bonus")
    made = made_in_game(c)
    return f"🔑 `{c['code']}` ({time_str})"[:256], (value + ("\n" + made if made else ""))[:1024]


def codes_embed(codes: list, page: int) -> discord.Embed:
    pages = max(1, -(-len(codes) // CODES_PER_PAGE))
    embed = discord.Embed(title=t("codes.list_title"), color=config_store.embed_color(), description=t("codes.list_description"))
    for c in codes[page * CODES_PER_PAGE:(page + 1) * CODES_PER_PAGE]:
        name, value = code_field(c)
        embed.add_field(name=name, value=value, inline=False)
    footer = t("codes.list_footer")
    if pages > 1:
        footer = t("codes.page", page=page + 1, pages=pages, count=len(codes)) + " • " + footer
    embed.set_footer(text=footer)
    return embed


class CodesPager(discord.ui.View):
    """/codes with many active codes: 10 per page (an embed shows at most 25 fields and 6000 characters)."""

    def __init__(self, codes: list, owner_id: int):
        super().__init__(timeout=600)
        self.codes, self.owner_id, self.page = codes, owner_id, 0
        self.pages = max(1, -(-len(codes) // CODES_PER_PAGE))
        self.message = None
        self._sync()

    def _sync(self):
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= self.pages - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(t("codes.use_own"), ephemeral=True)
        return False

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._sync()
        await interaction.response.edit_message(embed=codes_embed(self.codes, self.page), view=self)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._sync()
        await interaction.response.edit_message(embed=codes_embed(self.codes, self.page), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


async def owner_and_staff(interaction: discord.Interaction, owner_id: int, permission: str = "codes") -> bool:
    """Only the person who opened this window, and only while they may still use game actions (an administrator or a
    role chosen in /setup-roblox -> Control panel: taking the role away works at once, also in an open window)."""
    if interaction.user.id != owner_id:
        await interaction.response.send_message(t("errors.not_for_you"), ephemeral=True)
        return False
    return await staff_only(interaction, permission)


class CodeRemoveSelect(discord.ui.Select):
    def __init__(self, codes):
        options = [discord.SelectOption(label=c["code"][:100], description=describe_code(c), value=c["code"]) for c in codes]
        super().__init__(placeholder=t("codes.remove_placeholder"), min_values=1, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected = list(self.values)
        self.view.confirm.disabled = False
        await interaction.response.edit_message(
            content=t("codes.remove_selected", count=len(self.values), codes=", ".join(f"`{v}`" for v in self.values)),
            view=self.view)


class CodeRemoveView(Panel):
    close_button = False  # its Cancel removes the message

    def __init__(self, cog, admin_id: int, codes):
        super().__init__()
        self.cog, self.admin_id, self.selected = cog, admin_id, []
        self.add_item(CodeRemoveSelect(codes))
        self.confirm.label = t("codes.btn_remove_selected")
        self.cancel.label = t("common.cancel")
        self.confirm.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await owner_and_staff(interaction, self.admin_id)

    @discord.ui.button(label="Remove selected", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_finished():  # a double click: the first one already removes the codes
            return
        self.stop()
        await interaction.response.defer()
        message, removed = await self.cog.remove_codes_counted(self.selected)
        await show_in_place(interaction, content=message, view=CloseView())
        if removed:
            await action_log.discord_action(interaction, "code_remove", message)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await close_message(interaction, t("codes.remove_cancelled"))


class OverwriteView(Panel):
    """/code-add (or the form in /setup-roblox -> Codes) for a code that already exists: replace it only after a click."""
    close_button = False  # its Cancel removes the message

    def __init__(self, cog, admin_id: int, params: dict, panel: bool = False):
        super().__init__(timeout=300)
        self.cog, self.admin_id, self.params, self.panel = cog, admin_id, params, panel
        self.overwrite.label = t("codes.btn_overwrite")
        self.cancel.label = t("common.cancel")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await owner_and_staff(interaction, self.admin_id)

    @discord.ui.button(label="Replace", emoji="♻️", style=discord.ButtonStyle.danger)
    async def overwrite(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content=t("codes.overwriting", code=self.params["code"]), view=None)
        await self.cog.save_code(interaction, **self.params, panel=self.panel)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await close_message(interaction, t("codes.overwrite_cancelled"))


def code_reward(currency_type: str, currency_amount: int, exp_amount: int, item_reward: str, item_key: str) -> tuple:
    """(lines for Discord, the reward as the game reads it) of a code."""
    duration_sec, is_temp = ITEM_DURATIONS.get(item_key, (0, 0))
    lines, reward = [], {}
    if _chosen(currency_type) and currency_amount > 0:
        lines.append(f"• **{currency_amount:,}** {currency_type}")
        reward["currency"] = {"name": currency_type, "amount": currency_amount}
    if exp_amount > 0:
        lines.append(f"• **+{exp_amount:,}** EXP")
        reward["exp"] = exp_amount
    if _chosen(item_reward):
        suffix = f" *({duration_label(item_key)})*" if is_temp else f" *({t('codes.permanent')})*"
        lines.append(f"• **{item_reward}**{suffix}")
        reward["item"] = {"name": item_reward, "is_temporary": bool(is_temp), "duration_seconds": duration_sec}
    return lines, reward


def draft_embed(params: dict, replaces: str = "") -> discord.Embed:
    """A code from the /setup-roblox form before it is saved: nothing reaches the game until ✅ Save."""
    lines, reward = code_reward(params["currency_type"], params["currency_amount"], params["exp_amount"],
                                params["item_reward"], params["item_key"])
    embed = discord.Embed(title=t("codes.draft_title", code=params["code"])[:256], description=t("codes.draft_description"),
                          color=discord.Color.orange())
    embed.add_field(name=t("codes.validity"), value=duration_label(params["validity"]), inline=True)
    embed.add_field(name=t("codes.rewards"), value="\n".join(lines) or t("codes.draft_no_rewards"), inline=False)
    warnings = roblox_kit.reward_warnings(roblox_kit.game_scan(), reward) + catalog.robux_warnings(reward) if reward else []
    if warnings:
        embed.add_field(name=t("codes.draft_warnings"), value="\n".join(f"⚠️ {w}" for w in warnings)[:1024], inline=False)
    if replaces:
        embed.add_field(name=t("codes.draft_replaces_title"), value=t("codes.draft_replaces", rewards=replaces)[:1024],
                        inline=False)
    embed.set_footer(text=t("codes.draft_footer"))
    return embed


class CodeExtrasModal(discord.ui.Modal):
    """EXP and how long the item lasts: the parts of a code that don't fit in the first form (5 fields at most).
    Changes only the draft: the code reaches the game when the admin clicks ✅ Save."""

    def __init__(self, view: "CodeDraftView"):
        params = view.params
        super().__init__(title=t("codes.extras_title", code=params["code"])[:45])
        self.draft = view
        self.exp = discord.ui.TextInput(label=t("codes.extras_exp"), max_length=15, required=False, placeholder="500",
                                        default=str(params["exp_amount"]) if params["exp_amount"] else None)
        self.add_item(self.exp)
        self.duration = None
        if _chosen(params["item_reward"]):
            self.duration = discord.ui.Select(options=[
                discord.SelectOption(label=t(f"duration.choice.{key}")[:100], value=key, default=key == params["item_key"])
                for key in ITEM_DURATIONS])
            self.add_item(discord.ui.Label(text=t("codes.extras_duration"), component=self.duration))

    async def on_submit(self, interaction: discord.Interaction):
        if not await staff_only(interaction, "codes"):
            return
        if self.draft.closed:  # ⚙️ opened, then the draft was saved or cancelled before this form was sent
            await interaction.response.send_message(t("codes.draft_closed"), ephemeral=True)
            return
        digits = re.sub(r"[\s_.,]", "", self.exp.value or "")
        if digits and (not (digits.isascii() and digits.isdigit()) or int(digits) > MAX_AMOUNT):
            await interaction.response.send_message(t("codes.err_exp", max=f"{MAX_AMOUNT:,}"), ephemeral=True)
            return
        self.draft.params = dict(self.draft.params, exp_amount=int(digits or 0))
        if self.duration is not None and self.duration.values:
            self.draft.params["item_key"] = self.duration.values[0]
        draft = self.draft
        if draft.is_finished():  # the draft removed itself while the form was open: nothing is lost, a new one comes
            draft = CodeDraftView(draft.cog, draft.admin_id, draft.params, draft.replaces)
            await send_panel(interaction, draft, embed=draft_embed(draft.params, draft.replaces))
            return
        await interaction.response.defer()
        await show_in_place(interaction, view=draft, embed=draft_embed(draft.params, draft.replaces))


class CodeDraftView(Panel):
    """A code from the /setup-roblox form, not saved yet: ⚙️ adds EXP or the item's time, ✅ saves it and sends it to
    the game, Cancel drops it. A code is never changed after it went live from here. Everything happens in this one
    message: the draft becomes the "replace?" question or the result."""
    close_button = False  # its Cancel removes the message

    def __init__(self, cog, admin_id: int, params: dict, replaces: str = ""):
        super().__init__()
        self.cog, self.admin_id, self.params, self.replaces = cog, admin_id, params, replaces
        self.closed = False  # saved or cancelled (not just removed after a while)
        self.save.label = t("codes.btn_save")
        self.extras.label = t("codes.btn_extras")
        self.cancel.label = t("common.cancel")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await owner_and_staff(interaction, self.admin_id)

    @discord.ui.button(label="Save the code", emoji="✅", style=discord.ButtonStyle.success)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:  # checked again: a code needs a reward, and the game catalog may have changed since the form
            params = code_params(**self.params)
        except CodeError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        self.closed = True
        self.stop()
        await interaction.response.defer()  # the draft message itself turns into the answer
        await self.cog.add_code(interaction, params, panel=True)

    @discord.ui.button(label="EXP and item time", emoji="⚙️", style=discord.ButtonStyle.secondary)
    async def extras(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.hold_for_form()
        await interaction.response.send_modal(CodeExtrasModal(self))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.closed = True
        self.stop()
        await close_message(interaction, t("codes.draft_cancelled"))


class GameCodes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.clean_expired_codes.start()

    def cog_unload(self):
        self.clean_expired_codes.cancel()

    @tasks.loop(minutes=5)
    async def clean_expired_codes(self):
        try:
            await database.expire_old_codes()
        except Exception as e:  # e.g. "database is locked" for a moment: try again in 5 minutes
            log.warning("Could not mark expired codes: %s", e)

    def _choices(self, names: list, current: str):
        choices = [app_commands.Choice(name=n[:100], value=n[:100]) for n in names if current.lower() in n.lower()]
        if not names:
            # Nothing picked in /setup-roblox yet: the typed text still works, with a hint where names come from
            choices = ([app_commands.Choice(name=current[:100], value=current[:100])] if current.strip() else []) + \
                [app_commands.Choice(name=t("codes.no_names_hint")[:100], value=NONE)]
        return (choices + [app_commands.Choice(name=t("codes.none_option"), value=NONE)])[:25]

    async def currency_autocomplete(self, interaction: discord.Interaction, current: str):
        return self._choices(catalog.names_for("currencies", economy().get("currencies", [])), current)

    async def item_autocomplete(self, interaction: discord.Interaction, current: str):
        """Items and pets, the game catalog's exact names first (a pet shows its rarity)."""
        eco = economy()
        rarities = catalog.rarities(catalog.game_catalog())
        all_names = catalog.reward_names(eco.get("items", []), eco.get("pets", []))
        if not all_names:
            return self._choices([], current)
        names = [n for n in all_names if current.lower() in n.lower()]
        choices = []
        for name in names[:24]:
            rarity = rarities.get(catalog.key(name), "")
            choices.append(app_commands.Choice(name=(f"{name} · {rarity}" if rarity else name)[:100], value=name[:100]))
        return choices + [app_commands.Choice(name=t("codes.none_option"), value=NONE)]

    async def active_codes_autocomplete(self, interaction: discord.Interaction, current: str):
        active_codes = await database.get_active_game_codes()
        return [
            app_commands.Choice(name=t("codes.autocomplete", code=c["code"],
                                       date=time.strftime("%Y-%m-%d", time.gmtime(int(c["created_at"] or 0))))[:100],
                                value=c["code"])
            for c in active_codes if current.upper() in c["code"].upper()
        ][:25]

    @app_commands.command(name="code-add", description=L("cmd.code_add"))
    @app_commands.guild_only()
    @app_commands.describe(
        code=L("cmd.code_add.code"),
        code_validity=L("cmd.code_add.code_validity"),
        currency_type=L("cmd.code_add.currency_type"),
        currency_amount=L("cmd.code_add.currency_amount"),
        exp_amount=L("cmd.code_add.exp_amount"),
        item_reward=L("cmd.code_add.item_reward"),
        item_duration=L("cmd.code_add.item_duration")
    )
    @app_commands.choices(
        code_validity=[app_commands.Choice(name=L(f"duration.choice.{key}"), value=key) for key in CODE_VALIDITY],
        item_duration=[app_commands.Choice(name=L(f"duration.choice.{key}"), value=key) for key in ITEM_DURATIONS]
    )
    @app_commands.autocomplete(currency_type=currency_autocomplete, item_reward=item_autocomplete)
    async def code_add(
        self,
        interaction: discord.Interaction,
        code: app_commands.Range[str, 1, 30],
        code_validity: app_commands.Choice[str],
        currency_type: str = NONE,
        currency_amount: app_commands.Range[int, 0, MAX_AMOUNT] = 0,
        exp_amount: app_commands.Range[int, 0, MAX_AMOUNT] = 0,
        item_reward: str = NONE,
        item_duration: app_commands.Choice[str] = None
    ):
        try:
            params = code_params(code, code_validity.value, currency_type, currency_amount, exp_amount, item_reward,
                                 item_duration.value if item_duration else "permanent")
        except CodeError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await self.add_code(interaction, params)

    async def add_code(self, interaction: discord.Interaction, params: dict, panel: bool = False):
        """Saves a checked code (code_params), or first asks before replacing an active code with the same name.
        panel: the answer is only for the admin (the /setup-roblox form), possibly after the interaction was answered."""
        existing = await database.get_game_code(params["code"])
        if is_live(existing):
            view = OverwriteView(self, interaction.user.id, params, panel=panel)
            text = t("codes.exists", code=params["code"], rewards=describe_code(existing))
            if panel and interaction.response.is_done():  # the panel's draft becomes the question
                await show_in_place(interaction, view=view, content=text, embed=None)
            else:
                await send_panel(interaction, view, content=text)
            return
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=panel, thinking=panel)
        await self.save_code(interaction, **params, panel=panel)

    async def save_code(self, interaction: discord.Interaction, code: str, validity: str, currency_type: str,
                        currency_amount: int, exp_amount: int, item_reward: str, item_key: str, panel: bool = False):
        embed = await self.store_code(interaction.user, code, validity, currency_type, currency_amount, exp_amount,
                                      item_reward, item_key)
        if panel:  # in place of the draft (or the "replace?" question), with ✖️ Close
            await show_in_place(interaction, view=CloseView(), content=None, embed=embed)
        else:
            await interaction.followup.send(embed=embed, ephemeral=False)  # /code-add answers in the channel
        await action_log.discord_action(interaction, "code_add", embed)

    async def store_code(self, user, code: str, validity: str, currency_type: str, currency_amount: int, exp_amount: int,
                         item_reward: str, item_key: str) -> discord.Embed:
        """Saves the code, sends the codes to the game and returns the reply for the admin."""
        now = int(time.time())
        validity_sec = CODE_VALIDITY.get(validity, 0)
        expires_at = (now + validity_sec) if validity_sec > 0 else 0

        has_currency = _chosen(currency_type) and currency_amount > 0
        has_item = _chosen(item_reward)
        duration_sec, is_temp = ITEM_DURATIONS.get(item_key, (0, 0))

        await database.add_game_code(
            code=code,
            currency=currency_type if has_currency else None,
            currency_amount=currency_amount if has_currency else 0,
            exp_amount=exp_amount,
            item=item_reward if has_item else None,
            item_duration_label=item_key,
            item_duration_sec=duration_sec,
            is_temporary=is_temp,
            expires_at=expires_at,
            created_by=user.id
        )

        embed = discord.Embed(title=t("codes.created_title"), color=discord.Color.green(),
                              description=t("codes.created_description", code=code))
        embed.add_field(name=t("codes.validity"), value=f"<t:{expires_at}:R>" if expires_at > 0 else t("codes.unlimited"), inline=True)

        rewards_desc, reward = code_reward(currency_type, currency_amount, exp_amount, item_reward, item_key)
        embed.add_field(name=t("codes.rewards"), value="\n".join(rewards_desc) if rewards_desc else t("codes.no_rewards"), inline=False)

        sync_cog = self.bot.get_cog("CloudSync")
        if sync_cog:
            sync_text = await sync_cog.sync_after_change()
            scan = roblox_kit.game_scan()
            warnings = roblox_kit.reward_warnings(scan, reward) + catalog.robux_warnings(reward)
            if warnings:
                sync_text += "\n" + "\n".join(f"⚠️ {w}" for w in warnings)
            elif rewards_desc and cloud_sync.status() != "off" and not scan:
                sync_text += "\n" + t("codes.names_reminder")
            embed.add_field(name=t("codes.sync_field"), value=sync_text[:1024], inline=False)
        embed.set_footer(text=t("codes.created_by", user=user.display_name))
        return embed

    async def remove_codes(self, codes: list) -> str:
        """Deactivates the given codes and syncs the game once. Returns a ready message."""
        return (await self.remove_codes_counted(codes))[0]

    async def remove_codes_counted(self, codes: list) -> tuple:
        """remove_codes() and how many codes it really removed (0: all of them had already ended)."""
        removed, missing = [], []
        for code in codes:
            existing = await database.get_game_code(code)
            if existing and existing["is_active"]:
                await database.delete_game_code(code)
                removed.append(code.upper())
            else:
                missing.append(code.upper())
        lines = []
        if removed:
            lines.append(t("codes.removed_list", count=len(removed), codes=", ".join(f"`{c}`" for c in removed)))
        if missing:
            lines.append(t("codes.already_inactive", codes=", ".join(f"`{c}`" for c in missing)))
        sync_cog = self.bot.get_cog("CloudSync")
        if removed and sync_cog:
            lines.append(await sync_cog.sync_after_change())
        return "\n".join(lines)[:1900], len(removed)

    # Removes one code (from autocomplete) or several at once from a list
    @app_commands.command(name="code-remove", description=L("cmd.code_remove"))
    @app_commands.guild_only()
    @app_commands.describe(code=L("cmd.code_remove.code"))
    @app_commands.autocomplete(code=active_codes_autocomplete)
    async def code_remove(self, interaction: discord.Interaction, code: str = None):
        if code:
            existing = await database.get_game_code(code)
            if not existing or not existing["is_active"]:
                await interaction.response.send_message(t("codes.not_found", code=code.upper()), ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            message, removed = await self.remove_codes_counted([code])
            await interaction.followup.send(message, ephemeral=True)
            if removed:
                await action_log.discord_action(interaction, "code_remove", message)
            return

        active = await database.get_active_game_codes()
        if not active:
            await interaction.response.send_message(t("codes.none_active"), ephemeral=True)
            return
        note = "\n" + t("codes.list_limited", total=len(active)) if len(active) > 25 else ""
        await send_panel(interaction, CodeRemoveView(self, interaction.user.id, active[:25]), content=t("codes.remove_intro") + note)

    @app_commands.command(name="codes", description=L("cmd.codes"))
    @app_commands.guild_only()
    async def codes_list(self, interaction: discord.Interaction):
        active_codes = list(await database.get_active_game_codes())
        if not active_codes:
            embed = discord.Embed(title=t("codes.list_title"), color=config_store.embed_color(), description=t("codes.list_empty"))
            await interaction.response.send_message(embed=embed)
            return
        if len(active_codes) <= CODES_PER_PAGE:
            await interaction.response.send_message(embed=codes_embed(active_codes, 0))
            return
        view = CodesPager(active_codes, interaction.user.id)
        await interaction.response.send_message(embed=codes_embed(active_codes, 0), view=view)
        try:
            view.message = await interaction.original_response()
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(GameCodes(bot))
