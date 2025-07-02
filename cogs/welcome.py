import discord
from discord.ext import commands

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        # Lấy thông tin từ config
        welcome_channel_id = self.bot.config["channels"]["welcome"]
        channel = member.guild.get_channel(welcome_channel_id)
        if not channel:
            return

        # Gửi tin nhắn chào mừng
        await channel.send(f"🔥 Một thằng lồn mới vào trại: **{member.name}**!")

async def setup(bot):
    await bot.add_cog(Welcome(bot))
