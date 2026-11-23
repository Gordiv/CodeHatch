import discord
from discord import app_commands
from discord.ext import commands

from utils import access, config_store
from utils.i18n import L, t
from utils.version import VERSION


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description=L("cmd.help"))
    @app_commands.guild_only()
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(title=t("help.title"), description=t("help.description"), color=config_store.embed_color())
        if access.is_admin(interaction):
            embed.add_field(name=t("help.config_title"), value=t("help.config"), inline=False)
            embed.add_field(name=t("help.codes_title"), value=t("help.codes"), inline=False)
            embed.add_field(name=t("help.live_title"), value=t("help.live"), inline=False)
        embed.set_footer(text=f"CodeHatch {VERSION}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Help(bot))
