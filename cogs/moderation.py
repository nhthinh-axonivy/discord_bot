import discord
from discord.ext import commands

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str):
        """Cảnh cáo thành viên"""
        self.bot.db["warnings"].update_one(
            {"user_id": member.id, "guild_id": ctx.guild.id},
            {"$push": {"warnings": {"reason": reason, "mod": ctx.author.id}}},
            upsert=True
        )
        await ctx.send(f"{member.name} đã bị cảnh cáo vì: {reason}")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str):
        """Cấm thành viên"""
        await member.ban(reason=reason)
        await ctx.send(f"{member.name} đã bị cấm khỏi trại!")

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str):
        """Đuổi thành viên"""
        await member.kick(reason=reason)
        await ctx.send(f"{member.name} đã bị đuổi khỏi trại!")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
