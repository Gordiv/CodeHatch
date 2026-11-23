"""/tutorial: a step-by-step course for a new owner, inside the bot.

Chapters come from locales/tutorial_<language>.json. Each chapter explains one area in plain words, shows the live
state on this server (✅ / ⚠️) and has buttons that open the right panel, so the owner never has to guess where
something is. After the bot joins a server it posts a short welcome that points to /tutorial.
"""
import json
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from cogs import setup as setup_cog
from cogs.setup_guide import GuideView
from utils import access, catalog, cloud_sync, config_store, database, i18n, roblox_kit
from utils.i18n import L, t
from utils.ui import PANEL_TIMEOUT, AdminView, send_panel

PERMISSIONS = ["view_channel", "send_messages", "embed_links", "read_message_history"]
# Checks that need the game's reports (read once per chapter, not once per check)
GAME_CHECKS = {"kit", "names", "catalog", "eggs", "events"}
REQUIRED = ("title", "intro", "fields")
_chapters = {}
log = logging.getLogger("tutorial")


def _valid(items) -> list:
    """Chapters that have everything a page needs (a damaged file never breaks the tutorial)."""
    if not isinstance(items, list):
        return []
    good = []
    for chapter in items:
        if isinstance(chapter, dict) and all(chapter.get(k) is not None for k in REQUIRED):
            chapter.setdefault("menu", "")
            chapter.setdefault("emoji", "📖")
            good.append(chapter)
    return good


def _load(lang: str) -> list:
    if lang not in _chapters:
        try:
            with open(os.path.join(i18n.LOCALES_DIR, f"tutorial_{lang}.json"), encoding="utf-8") as f:
                _chapters[lang] = _valid(json.load(f))
        except (OSError, ValueError) as e:
            log.error("locales/tutorial_%s.json can't be read (%s): English chapters are used instead.", lang, e)
            _chapters[lang] = None
    return _chapters[lang] or (_load(i18n.DEFAULT_LANGUAGE) if lang != i18n.DEFAULT_LANGUAGE else [])


def chapters(lang: str = None) -> list:
    """Chapters for this language."""
    return _load(lang or i18n.language())


def _color() -> int:
    return config_store.embed_color()


def _mark(ok, text: str) -> str:
    return f"{'✅' if ok else '⚠️'} {text}"


# ---------- Live checks shown under each chapter ----------

async def check_lines(check: str, guild: discord.Guild, client=None) -> list:
    cfg = config_store.load()
    roblox, ai = (cfg.get(k, {}) for k in ("roblox", "ai_support"))
    me = guild.me
    if check == "bot_permissions":
        perms = me.guild_permissions
        if perms.administrator:
            return [_mark(True, t("tut.chk_admin"))]
        missing = [p for p in PERMISSIONS if not getattr(perms, p)]
        return [_mark(not missing, t("tut.chk_perms_ok") if not missing else t("tut.chk_perms_missing", perms=", ".join(missing)))]
    if check == "language":
        return [_mark(True, t("tut.chk_language", language=i18n.LANGUAGES[i18n.language()]))]
    if check == "channels":
        done = bool(ai.get("developer_bug_channel_id"))
        return [_mark(done, t("tut.chk_channels_ok") if done else t("tut.chk_channels_missing"))]
    if check == "game":
        ok = bool(roblox.get("universe_id") and roblox.get("place_id"))
        return [_mark(ok, t("tut.chk_game_ok", place=roblox.get("place_id")) if ok else t("tut.chk_game_missing"))]
    if check == "connection":
        status = cloud_sync.status()
        return [_mark(status == "ready", t(f"setup.sync_status.{status}"))]
    if check == "kit":
        line = roblox_kit.status_line()
        return [line] if line else [_mark(False, t("tut.chk_kit_needs_connection"))]
    if check == "names":
        scan = roblox_kit.game_scan()
        eco = config_store.read_json("game_economy.json", {})
        lines = [_mark(bool(scan), t("tut.chk_scan_ok", names=len(scan["values"]) + len(scan["attributes"]))
                       if scan else t("tut.chk_scan_missing"))]
        currencies = eco.get("currencies", []) if eco.get("configured") else []
        lines.append(_mark(bool(currencies), t("tut.chk_currencies", names=", ".join(currencies[:10]))
                           if currencies else t("tut.chk_currencies_missing")))
        return lines
    if check == "catalog":
        cat = catalog.game_catalog()
        lines = [_mark(catalog.has_names(cat), catalog.summary(cat).lstrip("📒 "))]
        problems = catalog.problems(cat)
        if problems:
            lines.append(_mark(False, t("tut.chk_catalog_problems", count=len(problems))))
        return lines
    if check == "codes":
        count = len(await database.get_active_game_codes())
        return [_mark(count > 0, t("tut.chk_codes", count=count))]
    if check == "control_panel":
        from cogs import game_panel
        cfg = game_panel.settings(guild.id)
        channel = game_panel.panel_channel(guild, cfg["channel_id"])
        posted = bool(channel and cfg["message_id"])
        roles = game_panel.staff_roles(guild)
        return [_mark(posted, t("tut.chk_gpanel_posted", channel=channel.mention) if posted else t("tut.chk_gpanel_missing")),
                _mark(True, t("tut.chk_gpanel_roles", roles=", ".join(r.mention for r in roles)) if roles
                      else t("tut.chk_gpanel_admins_only"))]
    if check == "eggs":
        scan = roblox_kit.game_scan()
        eggs = len(await database.get_active_eggs())
        lines = [_mark(eggs > 0, t("tut.chk_eggs", count=eggs))]
        if scan:
            lines.append(_mark(bool(scan["spots"]), t("tut.chk_spots", count=len(scan["spots"]))))
        return lines
    if check == "events":
        scan = roblox_kit.game_scan()
        events = len(await database.get_active_live_events())
        lines = [_mark(events > 0, t("tut.chk_events", count=events))]
        if scan:
            used = scan["multipliers"]
            lines.append(_mark(bool(used), t("tut.chk_multipliers", names=", ".join(used[:10])) if used
                               else t("tut.chk_multipliers_missing")))
        return lines
    if check == "launcher":
        launcher = os.getenv("BOT_LAUNCHER") or ""
        return [_mark(bool(launcher), t("tut.chk_launcher_ok", launcher=launcher) if launcher else t("tut.chk_launcher_manual"))]
    if check == "servers":
        lines = [_mark(access.is_home_guild(guild.id), t("tut.chk_home_ok") if access.is_home_guild(guild.id)
                       else t("tut.chk_home_missing"))]
        public = await access.bot_is_public(client) if client is not None else None
        if public is not None:
            lines.append(_mark(not public, t("tut.chk_public_off") if not public else t("tut.chk_public_on")))
        return lines
    return []


# ---------- Buttons that open the right place ----------

ACTIONS = {
    "setup": "📋", "setup_roblox": "🎮", "guide": "📚", "channels": "📡", "servers": "🌐", "diagnostics": "🩺",
    "game": "🎮", "connection": "🔑", "kit": "📥", "names": "🔍", "catalog": "📒", "codes": "📜", "eggs": "🥚", "events": "⚡",
    "gifts": "🎁", "player": "👤", "control_panel": "🕹️",
    "check": "🧪",
}


async def run_action(action: str, interaction: discord.Interaction):
    from cogs import setup_roblox  # imports this module (the 📖 button of /setup-roblox)
    if action == "setup":
        await setup_cog.send_setup_panel(interaction)
    elif action == "setup_roblox":
        await setup_roblox.send_roblox_panel(interaction)
    elif action == "guide":
        view = GuideView(_color())
        await send_panel(interaction, view, embed=view.embed())
    elif action == "channels":
        view = setup_cog.ChannelsView()
        await send_panel(interaction, view, content=view.text())
    elif action == "servers":
        await interaction.response.defer(ephemeral=True, thinking=True)
        await send_panel(interaction, setup_cog.ServersView(interaction.client, interaction.guild),
                         embed=await setup_cog.build_servers_embed(interaction.client, interaction.guild))
    elif action == "diagnostics":
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.followup.send(embed=await setup_cog.run_diagnostics(interaction.guild, interaction.client), ephemeral=True)
    elif action == "game":
        await interaction.response.send_modal(setup_cog.GameModal(config_store.get("roblox")))
    elif action == "connection":
        await send_panel(interaction, setup_cog.CloudSyncView(), embed=setup_cog.build_sync_embed())
    elif action == "kit":
        await interaction.response.defer(ephemeral=True, thinking=True)
        await roblox_kit.refresh(force=True)
        await interaction.followup.send(embed=setup_cog.build_kit_embed(roblox_kit.evaluate()), ephemeral=True)
    elif action == "names":
        await interaction.response.defer(ephemeral=True, thinking=True)
        await roblox_kit.refresh(force=True)
        view = setup_roblox.GameNamesView()
        await send_panel(interaction, view, embed=view.embed())
    elif action == "catalog":
        await interaction.response.defer(ephemeral=True, thinking=True)
        await roblox_kit.refresh(force=True)
        await send_panel(interaction, setup_roblox.CatalogView(), embed=setup_roblox.catalog_embed())
    elif action in ("codes", "eggs", "events"):
        await interaction.response.defer(ephemeral=True, thinking=True)
        view = {"codes": setup_roblox.CodesView, "eggs": setup_roblox.EggsView, "events": setup_roblox.EventsView}[action]()
        await send_panel(interaction, view, embed=await view.embed())
    elif action == "gifts":
        view = setup_roblox.GiftsView()
        await send_panel(interaction, view, embed=view.embed())
    elif action == "player":
        await setup_roblox.open_player_lookup(interaction)
    elif action == "control_panel":
        from cogs import game_panel
        await game_panel.send_manager(interaction)
    elif action == "check":
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.followup.send(embed=await setup_roblox.run_checks(), ephemeral=True)


# ---------- The tutorial view ----------

class ChapterSelect(discord.ui.Select):
    """At most 25 chapters fit in a menu; with more, the 25 around the current one are shown."""

    def __init__(self, items: list, current: int):
        start = max(0, min(current - 12, len(items) - 25))
        options = [discord.SelectOption(label=f"{i + 1}. {c['title']}"[:100], description=(c.get("menu") or "")[:100] or None,
                                        emoji=c.get("emoji") or None, value=str(i), default=i == current)
                   for i, c in list(enumerate(items))[start:start + 25]]
        super().__init__(placeholder=t("tut.placeholder"), options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        await self.view.show(interaction, int(self.values[0]))


class ActionButton(discord.ui.Button):
    def __init__(self, action: str):
        super().__init__(label=t(f"tut.act_{action}")[:80], emoji=ACTIONS.get(action), style=discord.ButtonStyle.success, row=2)
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        await run_action(self.action, interaction)


class TutorialView(AdminView):
    def __init__(self, guild: discord.Guild, index: int = 0, client=None):
        super().__init__(timeout=PANEL_TIMEOUT)  # read for longer than other panels: removes itself after 14 minutes
        self.guild, self.client = guild, client
        self.items = chapters()
        self.index = max(0, min(index, len(self.items) - 1))
        if self.items:
            self._rebuild()

    def _rebuild(self):
        self.clear_items()
        self.add_item(ChapterSelect(self.items, self.index))
        back = discord.ui.Button(label=t("guide.back"), emoji="◀️", style=discord.ButtonStyle.secondary, disabled=self.index == 0,
                                 row=1)
        forward = discord.ui.Button(label=t("guide.next"), emoji="▶️", style=discord.ButtonStyle.primary,
                                    disabled=self.index >= len(self.items) - 1, row=1)
        again = discord.ui.Button(label=t("tut.recheck"), emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
        back.callback = lambda i: self.show(i, self.index - 1)
        forward.callback = lambda i: self.show(i, self.index + 1)
        again.callback = lambda i: self.show(i, self.index)
        for button in (back, forward, again):
            self.add_item(button)
        for action in self.items[self.index].get("actions", [])[:5]:
            if action in ACTIONS:
                self.add_item(ActionButton(action))

    async def embed(self) -> discord.Embed:
        if not self.items:
            return discord.Embed(title="📖", description=t("tut.no_chapters"), color=_color())
        chapter = self.items[self.index]
        embed = discord.Embed(title=f"{chapter.get('emoji', '📖')} {chapter['title']}"[:256], description=chapter["intro"][:4096],
                              color=_color())
        for field in chapter["fields"][:20]:
            if isinstance(field, (list, tuple)) and len(field) >= 2:
                embed.add_field(name=str(field[0])[:256], value=str(field[1])[:1024], inline=False)
        checks = chapter.get("checks", [])
        if GAME_CHECKS & set(checks):
            await roblox_kit.refresh_quick()  # once for the whole chapter (Discord waits only 3 s for the page)
        lines = []
        for check in checks:
            try:
                lines += await check_lines(check, self.guild, self.client)
            except Exception as e:  # a check must never break the tutorial
                log.warning("Tutorial check %s failed: %s", check, e)
        if lines:
            embed.add_field(name=t("tut.state_title"), value="\n".join(lines)[:1024], inline=False)
        embed.set_footer(text=t("tut.footer", step=self.index + 1, total=len(self.items)))
        return embed

    async def show(self, interaction: discord.Interaction, index: int):
        self.index = max(0, min(index, len(self.items) - 1))
        self._rebuild()
        # Some chapters ask Roblox about the game: answer Discord first, then show the page
        await interaction.response.defer()
        await interaction.edit_original_response(embed=await self.embed(), view=self)


def chapter_index(chapter_id: str) -> int:
    return next((i for i, c in enumerate(chapters()) if c.get("id") == chapter_id), 0)


async def send_tutorial(interaction: discord.Interaction, chapter: str = ""):
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)
    view = TutorialView(interaction.guild, chapter_index(chapter) if chapter else 0, interaction.client)
    await send_panel(interaction, view if view.items else None, embed=await view.embed())


# ---------- Welcome after joining a server ----------

def welcome_embed() -> discord.Embed:
    embed = discord.Embed(title=t("welcome.title"), description=t("welcome.description"), color=_color())
    embed.add_field(name=t("welcome.steps_title"), value=t("welcome.steps"), inline=False)
    embed.set_footer(text=t("welcome.footer"))
    return embed


def welcome_channel(guild: discord.Guild):
    channels = ([guild.system_channel] if guild.system_channel else []) + list(guild.text_channels)
    for channel in channels:
        perms = channel.permissions_for(guild.me)
        if perms.view_channel and perms.send_messages and perms.embed_links:
            return channel
    return None


class Tutorial(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tutorial", description=L("cmd.tutorial"))
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def tutorial(self, interaction: discord.Interaction):
        await send_tutorial(interaction)

    @commands.Cog.listener()
    async def on_home_guild_join(self, guild: discord.Guild):
        """Only on the owner's servers (main.py checks the server first; on a stranger's server the bot just leaves)."""
        channel = welcome_channel(guild)
        try:
            if channel:
                await channel.send(embed=welcome_embed())
            elif guild.owner:
                await guild.owner.send(embed=welcome_embed())
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(Tutorial(bot))
