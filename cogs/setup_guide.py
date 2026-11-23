import discord
from discord import app_commands
from discord.ext import commands

from utils import config_store, i18n
from utils.i18n import L, t
from utils.ui import PANEL_TIMEOUT, Panel, send_panel

REQUIRED = ("title", "intro", "fields")


def available_topics() -> list:
    """Topics of /setup-guide; topics with missing parts (a damaged file) are left out."""
    return [topic for topic in i18n.guide()
            if isinstance(topic, dict) and all(topic.get(k) is not None for k in REQUIRED)]


def build_embed(topics: list, index: int, color: int) -> discord.Embed:
    if not topics:
        return discord.Embed(title="📚", description=t("guide.no_topics"), color=color)
    topic = topics[index]
    embed = discord.Embed(title=f"{topic.get('emoji', '📚')} {topic['title']}"[:256], description=topic["intro"][:4096], color=color)
    for field in topic["fields"][:20]:
        if not isinstance(field, (list, tuple)) or len(field) < 2:
            continue
        embed.add_field(name=str(field[0])[:256], value=str(field[1])[:1024], inline=False)
    embed.set_footer(text=t("guide.footer", step=index + 1, total=len(topics)))
    return embed


class TopicSelect(discord.ui.Select):
    """At most 25 topics fit in a menu; with more, the 25 around the current one are shown."""

    def __init__(self, topics: list, current: int):
        start = max(0, min(current - 12, len(topics) - 25))
        options = [
            discord.SelectOption(label=f"{i + 1}. {topic['title']}"[:100], description=(topic.get("menu") or "")[:100] or None,
                                 emoji=topic.get("emoji") or None, value=str(i), default=(i == current))
            for i, topic in list(enumerate(topics))[start:start + 25]
        ]
        super().__init__(placeholder=t("guide.placeholder"), options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        await self.view.show(interaction, int(self.values[0]))


class GuideView(Panel):
    def __init__(self, color: int, index: int = 0):
        super().__init__(timeout=PANEL_TIMEOUT)  # read for longer than other panels: removes itself after 14 minutes
        self.topics = available_topics()
        self.color = color
        self.index = max(0, min(index, len(self.topics) - 1))
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        if not self.topics:
            return
        self.add_item(TopicSelect(self.topics, self.index))
        prev_btn = discord.ui.Button(label=t("guide.back"), emoji="◀️", style=discord.ButtonStyle.secondary,
                                     disabled=self.index == 0, row=1)
        next_btn = discord.ui.Button(label=t("guide.next"), emoji="▶️", style=discord.ButtonStyle.primary,
                                     disabled=self.index == len(self.topics) - 1, row=1)
        prev_btn.callback = lambda i: self.show(i, self.index - 1)
        next_btn.callback = lambda i: self.show(i, self.index + 1)
        self.add_item(prev_btn)
        self.add_item(next_btn)

    def embed(self) -> discord.Embed:
        return build_embed(self.topics, self.index, self.color)

    async def show(self, interaction: discord.Interaction, index: int):
        self.index = max(0, min(index, len(self.topics) - 1))
        self._rebuild()
        await interaction.response.edit_message(embed=self.embed(), view=self)


class SetupGuide(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup-guide", description=L("cmd.setup_guide"))
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def setup_guide(self, interaction: discord.Interaction):
        view = GuideView(config_store.embed_color())
        await send_panel(interaction, view, embed=view.embed())


async def setup(bot):
    await bot.add_cog(SetupGuide(bot))
