import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils import cloud_sync
from utils.i18n import L, t

log = logging.getLogger("cloud_sync")


def format_result(result: cloud_sync.SyncResult) -> str:
    if result.ok:
        text = f"🔄 {result.message}"
        return text + (f"\n⚠️ {result.warning}" if result.warning else "")
    return t("sync.failed_retry", message=result.message)


class CloudSync(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.failures = 0
        self.sync_loop.start()

    def cog_unload(self):
        self.sync_loop.cancel()

    # Retries failed uploads and removes expired codes from the game
    @tasks.loop(minutes=2)
    async def sync_loop(self):
        if cloud_sync.status() != "ready":
            return
        try:
            result = await cloud_sync.push_codes(force=False)
        except Exception as e:  # e.g. the database is busy for a moment: never stop the loop for good
            result = cloud_sync.SyncResult(False, str(e))
        if result.ok:
            if self.failures:
                log.info("Code sync works again.")
            self.failures = 0
            return
        self.failures += 1
        # The same error is written after the 1st, 2nd, 4th, 8th... failure in a row, not every 2 minutes
        if self.failures & (self.failures - 1) == 0:
            log.warning("Code sync failed (%s time(s) in a row): %s", self.failures, result.message)

    @sync_loop.before_loop
    async def before_sync_loop(self):
        await self.bot.wait_until_ready()

    async def sync_after_change(self) -> str:
        """Called after /code-add and /code-remove. Returns the text to append to the reply."""
        if cloud_sync.status() == "off":
            return t("sync.disabled_hint")
        return format_result(await cloud_sync.push_codes(force=True))

    @app_commands.command(name="sync-codes", description=L("cmd.sync_codes"))
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def sync_codes(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await cloud_sync.push_codes(force=True)
        await interaction.followup.send(format_result(result) if result.ok else f"⚠️ {result.message}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(CloudSync(bot))
