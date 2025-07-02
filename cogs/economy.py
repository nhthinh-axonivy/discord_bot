import discord
from discord.ext import commands
import random

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["bal"])
    async def balance(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        user_data = await self.bot.db.users.find_one({"user_id": target.id})
        money = user_data.get("money", 0) if user_data else 0
        await ctx.send(f"{target.name} có **{money} đồng**")

    @commands.command()
    async def work(self, ctx):
        earned = random.randint(50, 200)
        await self.bot.db.users.update_one(
            {"user_id": ctx.author.id},
            {"$inc": {"money": earned}},
            upsert=True
        )
        await ctx.send(f"{ctx.author.name} làm việc xong được **{earned} đồng**!")

async def setup(bot):
    await bot.add_cog(Economy(bot))
