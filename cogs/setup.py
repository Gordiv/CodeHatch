import re

import discord
from discord import app_commands
from discord.ext import commands

from utils import access, catalog, cloud_sync, config_store, env_store, i18n, roblox_api, roblox_kit
from utils.i18n import L, t
from utils.ui import AdminView, is_close_click, send_panel

API_KEY_PATTERN = re.compile(r"^[A-Za-z0-9+/=_\-.]{20,2000}$")
ECONOMY_FILE = "game_economy.json"
TEXT_CHANNELS = [discord.ChannelType.text, discord.ChannelType.news]
LANGUAGE_FLAGS = {"en": "🇬🇧", "pl": "🇵🇱", "es": "🇪🇸"}
# Discord: a text field holds at most 4000 characters; lists of names are limited so menus (25 options) can show them
FIELD_MAX = 4000
LIST_LIMITS = {"currencies": 25, "stats": 25, "items": 25, "pets": 100}


# ---------- Helpers ----------

def extract_id(text: str, pattern: str) -> int:
    text = (text or "").strip()
    m = re.search(pattern + r"/(\d+)", text)
    if m:
        return int(m.group(1))
    return int(text) if text.isdigit() else 0


def parse_list(text: str, limit: int = 25) -> list:
    seen, result = set(), []
    for part in re.split(r"[,;\n]", text or ""):
        part = part.strip()[:100]
        if part and part.lower() not in seen:
            seen.add(part.lower())
            result.append(part)
    return result[:limit]


def join_to_fit(names: list, limit: int = FIELD_MAX) -> str:
    """Names joined with commas, as many whole names as fit in a text field."""
    text = ""
    for name in names:
        candidate = f"{text}, {name}" if text else name
        if len(candidate) > limit:
            break
        text = candidate
    return text


# ---------- Main panel ----------

def _ch(i): return f"<#{i}>" if i else t("setup.not_set")


def sync_status_text(include_kit: bool = True) -> str:
    state = cloud_sync.load_state()
    text = t(f"setup.sync_status.{cloud_sync.status()}")
    if state.get("last_ok"):
        text += "\n" + t("setup.sync_last_ok", time=f"<t:{state['last_ok']}:R>")
    if state.get("last_error"):
        text += "\n" + t("setup.sync_last_error", error=state["last_error"])
    kit = roblox_kit.status_line() if include_kit else ""
    if kit:
        text += "\n" + kit
    return text[:1024]


def build_kit_embed(info: dict) -> discord.Embed:
    """The DiscordCodes.rbxmx file in the game: which version runs where and how to replace it."""
    colors = {"ok": discord.Color.green(), "publish": discord.Color.orange(), "outdated": discord.Color.orange(),
              "no_report": discord.Color.orange()}
    embed = discord.Embed(title=t("kit.title"), description=roblox_kit.status_line(info) or t("kit.sync_off"),
                          color=colors.get(info["status"], discord.Color.blurple()))
    lines = [t("kit.bot_version", version=info["bundled"] or "?")]
    for place in info["places"][:10]:
        lines.append(t("kit.place_line", place=place["place"], live=place["live"] or "—", studio=place["studio"] or "—"))
    embed.add_field(name=t("kit.versions"), value="\n".join(lines)[:1024], inline=False)
    embed.add_field(name=t("kit.steps_title"), value=t("kit.steps"), inline=False)
    embed.add_field(name=t("kit.keep_title"), value=t("kit.keep"), inline=False)
    embed.add_field(name=t("kit.window_title"), value=t("kit.window"), inline=False)
    embed.set_footer(text=t("kit.footer"))
    return embed


def build_sync_embed() -> discord.Embed:
    cfg = cloud_sync.settings()
    embed = discord.Embed(title=t("setup.sync_title"), description=t("setup.sync_description"), color=discord.Color.blurple())
    embed.add_field(name=t("setup.sync_status"), value=sync_status_text(), inline=False)
    embed.add_field(name=t("setup.sync_key_steps_title"), value=t("setup.sync_key_steps"), inline=False)
    embed.add_field(name=t("setup.sync_key"), value=t("setup.sync_key_saved") if cloud_sync.api_key() else t("setup.not_set"), inline=True)
    embed.add_field(name="Universe ID", value=f"`{cloud_sync.universe_id() or '—'}`", inline=True)
    embed.add_field(name=t("setup.sync_script_settings"), value=t("setup.sync_script_values", datastore=cfg["datastore_name"],
                                                                  entry=cfg["entry_key"], topic=cfg["topic"]), inline=False)
    embed.add_field(name=t("setup.sync_optional_title"), value=t("setup.sync_optional_scopes"), inline=False)
    return embed


def roblox_summary(cfg: dict) -> str:
    """Short state of the game connection for /setup; everything else is in /setup-roblox."""
    roblox = cfg.get("roblox", {})
    lines = [t("setup.roblox_game_ok", place=roblox["place_id"]) if roblox.get("universe_id") and roblox.get("place_id")
             else t("setup.roblox_game_missing"),
             t(f"setup.sync_status.{cloud_sync.status()}")]
    kit = roblox_kit.status_line()
    if kit:
        lines.append(kit)
    lines.append(t("setup.roblox_hint"))
    return "\n".join(lines)[:1024]


async def panel_embed(guild: discord.Guild) -> discord.Embed:
    await roblox_kit.refresh_quick()
    return build_panel(config_store.load(), guild)


def build_panel(cfg: dict, guild: discord.Guild = None) -> discord.Embed:
    ai, moderation = (cfg.get(k, {}) for k in ("ai_support", "moderation"))
    channels_done = bool(ai.get("developer_bug_channel_id"))
    steps = [channels_done]

    def icon(ok):
        return "✅" if ok else "⚠️"

    lang = i18n.language()
    embed = discord.Embed(title=t("setup.title"), description=t("setup.description", done=sum(steps), total=len(steps)),
                          color=config_store.embed_color())
    embed.add_field(name=t("setup.language_field"), value=f"{LANGUAGE_FLAGS[lang]} {i18n.LANGUAGES[lang]}", inline=False)
    channels = t("setup.channels_summary", bugs=_ch(ai.get("developer_bug_channel_id")),
                 log=_ch(moderation.get("log_channel_id")))
    embed.add_field(name=f"{icon(channels_done)} {t('setup.step_channels')}", value=channels[:1024], inline=False)
    embed.add_field(name=t("setup.roblox_field"), value=roblox_summary(cfg), inline=False)
    embed.set_footer(text=t("setup.footer_tutorial"))
    return embed


# ---------- Diagnostics ----------

OK, WARN, ERROR = "ok", "warn", "error"


async def run_diagnostics(guild: discord.Guild, bot=None) -> discord.Embed:
    cfg = config_store.load()
    me = guild.me
    lines = []  # (status, text)
    roblox, ai = (cfg.get(k, {}) for k in ("roblox", "ai_support"))

    def add(status, text):
        lines.append((status, text))

    def check_channel(label, cid, need, required=True):
        if not cid:
            add(WARN if required else OK, t("diag.not_set", label=label))
            return
        ch = guild.get_channel(cid)
        if not ch:
            add(ERROR, t("diag.channel_missing", label=label))
            return
        perms = ch.permissions_for(me)
        missing = [name for name in need if not getattr(perms, name)]
        if missing:
            add(ERROR, t("diag.channel_perms", label=label, channel=ch.mention, perms=", ".join(missing)))
        else:
            add(OK, f"✅ {label} ({ch.mention})")

    if bot is not None:
        public = await access.bot_is_public(bot)
        if public:
            add(WARN, t("diag.bot_public"))
        if not access.is_home_guild(guild.id):
            add(ERROR, t("diag.not_home"))

    check_channel(t("diag.bug_channel"), ai.get("developer_bug_channel_id"), ["view_channel", "send_messages", "embed_links"])
    check_channel(t("diag.log_channel"), config_store.for_guild(cfg, guild.id, "moderation").get("log_channel_id"),
                  ["view_channel", "send_messages", "embed_links"], required=False)
    sync_state = cloud_sync.status()
    if sync_state == "ready":
        add(OK, t("diag.sync_ok"))
        kit = roblox_kit.status_line()
        if kit:
            kit_status = roblox_kit.evaluate()["status"]
            add(OK if kit_status == "ok" else WARN, kit)
    elif sync_state != "off":
        add(ERROR, t("diag.sync_incomplete"))
    add(OK, t("diag.universe_ok")) if roblox.get("universe_id") else add(ERROR, t("diag.universe_missing"))

    if cfg.get("leaderboard", {}).get("datastore"):
        add(OK, t("diag.leaderboard_ok", datastore=cfg["leaderboard"]["datastore"]))

    problems = sum(1 for status, _ in lines if status == ERROR)
    warnings = sum(1 for status, _ in lines if status == WARN)
    color = discord.Color.red() if problems else discord.Color.orange() if warnings else discord.Color.green()
    return discord.Embed(title=t("diag.title"), description="\n".join(text for _, text in lines)[:4000],
                         color=color).set_footer(text=t("diag.footer_full", count=problems, warnings=warnings))


# ---------- Selects ----------

class ConfigChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, label, placeholder, targets, channel_types, row, optional=False):
        super().__init__(placeholder=placeholder, channel_types=channel_types, min_values=0 if optional else 1, max_values=1,
                         row=row)
        self.label, self.targets = label, targets

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0].id if self.values else 0
        config_store.set_values([(s, k, value) for s, k in self.targets])
        shown = " ".join(c.mention for c in self.values) or t("setup.not_set")
        await interaction.response.send_message(f"✅ **{self.label}:** {shown}", ephemeral=True)


class ChannelsView(AdminView):
    def __init__(self):
        super().__init__()
        self.add_item(ConfigChannelSelect(t("diag.bug_channel"), t("setup.ph_bug_channel"),
                                          [("ai_support", "developer_bug_channel_id")], TEXT_CHANNELS, 0))
        self.add_item(ConfigChannelSelect(t("diag.log_channel"), t("setup.ph_log_channel"),
                                          [("moderation", "log_channel_id")], TEXT_CHANNELS, 1, optional=True))

    def text(self) -> str:
        return t("setup.pick_channels")


class LanguageSelect(discord.ui.Select):
    # Always the last row of /setup, under every button
    def __init__(self):
        current = i18n.language()
        options = [discord.SelectOption(label=name, value=code, emoji=LANGUAGE_FLAGS[code], default=code == current)
                   for code, name in i18n.LANGUAGES.items()]
        super().__init__(placeholder="🌐 Language / Język / Idioma", min_values=1, max_values=1, options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        i18n.set_language(self.values[0])
        await interaction.response.defer()
        view = PanelView()
        view.message = self.view.message
        self.view.stop()
        await interaction.edit_original_response(embed=await panel_embed(interaction.guild), view=view)
        await interaction.followup.send(t("setup.language_changed"), ephemeral=True)


# ---------- Forms ----------

class GameModal(discord.ui.Modal):
    def __init__(self, roblox: dict):
        super().__init__(title=t("setup.game_modal_title"))
        self.place = discord.ui.TextInput(label=t("setup.game_place"), required=True, max_length=200,
                                          placeholder=t("setup.game_place_ph"), default=str(roblox.get("place_id") or ""))
        self.universe = discord.ui.TextInput(label=t("setup.game_universe"), required=False, max_length=30)
        for item in (self.place, self.universe):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        place_id = extract_id(self.place.value, r"games")
        universe_id = extract_id(self.universe.value, r"universes")
        if not place_id:
            await interaction.followup.send(t("setup.game_bad_place"), ephemeral=True)
            return

        try:
            place_universe = await roblox_api.universe_of_place(place_id)
            if universe_id and place_universe and place_universe != universe_id:
                await interaction.followup.send(t("setup.game_mismatch", place=place_id, universe=universe_id,
                                                  real=place_universe), ephemeral=True)
                return
            universe_id = universe_id or place_universe or 0
            if not universe_id:
                await interaction.followup.send(t("setup.game_not_found"), ephemeral=True)
                return
            game = await roblox_api.get_game(universe_id)
        except roblox_api.RobloxApiError as e:
            # Roblox didn't answer: that is not the same as "this game doesn't exist", nothing is saved
            await interaction.followup.send(t("setup.roblox_down", error=e), ephemeral=True)
            return
        game_name = (game or {}).get("name")

        previous = config_store.get("roblox").get("universe_id") or 0
        config_store.set_values([("roblox", "place_id", place_id), ("roblox", "universe_id", int(universe_id))])
        msg = t("setup.game_saved", name=game_name or t("setup.game_private"), place=place_id, universe=universe_id)
        if previous and int(previous) != int(universe_id):
            # Another game: the codes, events and eggs are sent to it again, and its reports are read from scratch
            await cloud_sync.reset_game_state()
            msg += "\n" + t("setup.game_changed")
            if cloud_sync.status() == "ready":
                result = await cloud_sync.push_codes(force=True)
                msg += "\n" + (f"✅ {result.message}" if result.ok else f"⚠️ {result.message}")
        await interaction.followup.send(msg, ephemeral=True)


class EconomyModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title=t("setup.economy_modal_title"))
        eco = config_store.read_json(ECONOMY_FILE, {})

        def field(key, required):
            return discord.ui.TextInput(
                label=t(f"setup.eco_{key}"), placeholder=t(f"setup.eco_{key}_ph"), required=required, max_length=FIELD_MAX,
                style=discord.TextStyle.paragraph, default=(join_to_fit(eco.get(key, [])) or None))
        self.currencies = field("currencies", True)
        self.stats = field("stats", False)
        self.items = field("items", False)
        self.pets = field("pets", False)
        for item in (self.currencies, self.stats, self.items, self.pets):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        eco = config_store.read_json(ECONOMY_FILE, {})
        typed = {key: parse_list(getattr(self, key).value, limit=1000) for key in LIST_LIMITS}
        eco.update({key: names[:LIST_LIMITS[key]] for key, names in typed.items()})
        eco["configured"] = True
        config_store.write_json(ECONOMY_FILE, eco)
        cut = [f"{t(f'setup.eco_{key}').split('(')[0].strip()} ({LIST_LIMITS[key]})" for key, names in typed.items()
               if len(names) > LIST_LIMITS[key]]
        note = ("\n" + t("setup.economy_cut", lists=", ".join(cut))) if cut else ""
        await interaction.response.send_message(
            t("setup.economy_saved", currencies=len(eco["currencies"]), stats=len(eco["stats"]), items=len(eco["items"]))
            + note + catalog.manual_note(("currencies", "items")),
            ephemeral=True)


class ApiKeyModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title=t("setup.key_modal_title"))
        self.key = discord.ui.TextInput(label=t("setup.key_label"), required=True, max_length=2000, placeholder=t("setup.key_ph"))
        self.add_item(self.key)

    async def on_submit(self, interaction: discord.Interaction):
        value = self.key.value.strip()
        if not API_KEY_PATTERN.match(value):
            await interaction.response.send_message(t("setup.key_invalid"), ephemeral=True)
            return
        env_store.set_env("ROBLOX_API_KEY", value)
        await interaction.response.send_message(t("setup.key_saved"), ephemeral=True)


class CloudSyncView(AdminView):
    close_row = 0  # the Studio file button stays alone in its row (it is the step people look for)

    def __init__(self):
        super().__init__()
        self.set_key.label = t("setup.btn_paste_key")
        self.toggle.label = t("setup.btn_toggle")
        self.test.label = t("setup.btn_test")
        self.refresh.label = t("setup.btn_refresh")
        self.kit.label = t("kit.btn")

    @discord.ui.button(label="Paste API key", emoji="🔑", style=discord.ButtonStyle.primary, row=0)
    async def set_key(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ApiKeyModal())

    @discord.ui.button(label="On / off", emoji="🔌", style=discord.ButtonStyle.secondary, row=0)
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        enabled = not cloud_sync.settings()["enabled"]
        config_store.set_values([("cloud_sync", "enabled", enabled)])
        await interaction.response.edit_message(embed=build_sync_embed(), view=self)

    @discord.ui.button(label="Test & sync", emoji="🧪", style=discord.ButtonStyle.success, row=0)
    async def test(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await cloud_sync.push_codes(force=True)
        if result.ok:
            text = f"✅ {result.message}"
            if result.warning:
                text += f"\n⚠️ {result.warning}"
            await roblox_kit.refresh(force=True)
            kit = roblox_kit.status_line()
            if kit:
                text += "\n" + kit
        else:
            text = f"❌ {result.message}"
        await interaction.followup.send(text, ephemeral=True)

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary, row=0)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await roblox_kit.refresh_quick(force=True)
        await interaction.edit_original_response(embed=build_sync_embed(), view=self)

    @discord.ui.button(label="Studio file", emoji="📥", style=discord.ButtonStyle.primary, row=1)
    async def kit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await roblox_kit.refresh(force=True)
        await interaction.followup.send(embed=build_kit_embed(roblox_kit.evaluate()), ephemeral=True)


# ---------- The owner's servers ----------

async def build_servers_embed(bot, guild: discord.Guild) -> discord.Embed:
    ids = access.home_guild_ids()
    lines = []
    for guild_id in ids:
        known = bot.get_guild(guild_id)
        name = discord.utils.escape_markdown(known.name) if known else t("servers.not_joined")
        lines.append(f"{'📍' if guild_id == guild.id else '•'} **{name}** (`{guild_id}`)")
    strangers = [g for g in bot.guilds if g.id not in ids]
    embed = discord.Embed(title=t("servers.title"), description=t("servers.description"), color=config_store.embed_color())
    embed.add_field(name=t("servers.list", count=len(ids)), value="\n".join(lines)[:1024] or "—", inline=False)
    if strangers:
        embed.add_field(name=t("servers.strangers"), value="\n".join(f"• {discord.utils.escape_markdown(g.name)} (`{g.id}`)"
                                                                     for g in strangers)[:1024], inline=False)
    public = await access.bot_is_public(bot)
    embed.add_field(name=t("servers.public_title"), value=t("servers.public_on") if public else t("servers.public_off"),
                    inline=False)
    embed.set_footer(text=t("servers.footer"))
    return embed


class AddServerModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title=t("servers.add_title"))
        self.view_ref = view
        self.server = discord.ui.TextInput(label=t("servers.add_label"), max_length=20, placeholder="123456789012345678")
        self.add_item(self.server)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.server.value.strip()
        if not raw.isdigit() or not 17 <= len(raw) <= 20:
            await interaction.response.send_message(t("servers.bad_id"), ephemeral=True)
            return
        access.add_home_guild(int(raw))
        await interaction.response.send_message(t("servers.added", guild=raw), ephemeral=True)


class RemoveServerSelect(discord.ui.Select):
    def __init__(self, bot, current_id: int):
        options = []
        for guild_id in access.home_guild_ids():
            if guild_id == current_id:
                continue
            known = bot.get_guild(guild_id)
            options.append(discord.SelectOption(label=(known.name if known else str(guild_id))[:100], value=str(guild_id),
                                                description=str(guild_id)))
        super().__init__(placeholder=t("servers.remove_ph"), options=options[:25] or [discord.SelectOption(label="—", value="0")],
                         disabled=not options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if not await access.is_bot_owner(interaction.client, interaction.user.id):
            await interaction.response.send_message(t("servers.owner_only"), ephemeral=True)
            return
        guild_id = int(self.values[0])
        access.remove_home_guild(guild_id)
        guild = interaction.client.get_guild(guild_id)
        if guild:
            try:
                await guild.leave()
            except discord.HTTPException:
                pass
        await interaction.response.send_message(t("servers.removed", guild=guild.name if guild else guild_id), ephemeral=True)


class ServersView(AdminView):
    def __init__(self, bot, guild: discord.Guild):
        super().__init__()
        self.bot, self.guild = bot, guild
        self.add_server.label = t("servers.btn_add")
        self.add_item(RemoveServerSelect(bot, guild.id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if is_close_click(interaction) or await access.is_bot_owner(interaction.client, interaction.user.id):
            return True  # any administrator may close this window, only the owner may change the list
        await interaction.response.send_message(t("servers.owner_only"), ephemeral=True)
        return False

    @discord.ui.button(label="Add a server ID", emoji="➕", style=discord.ButtonStyle.primary, row=0)
    async def add_server(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddServerModal(self))


# ---------- Panel ----------

class PanelView(AdminView):
    """/setup: the Discord side. Everything about the Roblox game is in /setup-roblox (the 🎮 button)."""

    def __init__(self):
        super().__init__()
        labels = {"channels": "setup.btn_channels", "roblox": "setup.btn_roblox", "diagnostics": "setup.btn_diagnostics",
                  "refresh": "setup.btn_refresh", "tutorial": "setup.btn_tutorial", "servers": "setup.btn_servers",
                  "permissions": "perm.btn_setup"}
        for attr, key in labels.items():
            getattr(self, attr).label = t(key)
        self.add_item(LanguageSelect())

    @discord.ui.button(label="Roblox game", emoji="🎮", style=discord.ButtonStyle.success, row=0)
    async def roblox(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.setup_roblox import send_roblox_panel  # setup_roblox imports this module
        await send_roblox_panel(interaction)

    @discord.ui.button(label="Channels", emoji="📡", style=discord.ButtonStyle.primary, row=0)
    async def channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChannelsView()
        await send_panel(interaction, view, content=view.text())

    @discord.ui.button(label="Permissions", emoji="🛡️", style=discord.ButtonStyle.primary, row=0)
    async def permissions(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.game_panel import send_permissions  # game_panel imports utils only, but keep setup light
        await send_permissions(interaction)

    @discord.ui.button(label="Tutorial", emoji="📖", style=discord.ButtonStyle.secondary, row=0)
    async def tutorial(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tutorial import send_tutorial  # tutorial imports this module
        await send_tutorial(interaction)

    @discord.ui.button(label="Diagnostics", emoji="🩺", style=discord.ButtonStyle.secondary, row=1)
    async def diagnostics(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.followup.send(embed=await run_diagnostics(interaction.guild, interaction.client), ephemeral=True)

    @discord.ui.button(label="Servers", emoji="🌐", style=discord.ButtonStyle.secondary, row=1)
    async def servers(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        view = ServersView(interaction.client, interaction.guild)
        await send_panel(interaction, view, embed=await build_servers_embed(interaction.client, interaction.guild))

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.edit_original_response(embed=await panel_embed(interaction.guild), view=self)


async def send_setup_panel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    await send_panel(interaction, PanelView(), embed=await panel_embed(interaction.guild))


class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description=L("cmd.setup"))
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def setup_command(self, interaction: discord.Interaction):
        await send_setup_panel(interaction)


async def setup(bot):
    await bot.add_cog(Setup(bot))
