import discord
from discord.ext import commands
import random
from views.game_buttons import DiceGameView

class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def xidach(self, ctx, bet: int):
        if bet <= 0:
            return await ctx.send("Số tiền cược phải lớn hơn 0!")

        user_data = await self.bot.db.users.find_one({"user_id": ctx.author.id})
        if not user_data or user_data.get("money", 0) < bet:
            return await ctx.send("Mày không đủ tiền để cược!")

        view = DiceGameView(bot=self.bot, bet=bet, user=ctx.author)
        await ctx.send(f"{ctx.author.name} đã đặt cược **{bet} đồng**!", view=view)

async def setup(bot):
    await bot.add_cog(Games(bot))
