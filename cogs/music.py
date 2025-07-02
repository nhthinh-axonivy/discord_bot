import discord
from discord.ext import commands
from discord.utils import get
from discord import FFmpegPCMAudio
import asyncio
import yt_dlp

YTDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}  # Lưu queue theo guild.id
        self.votes = {}   # Lưu thông tin vote skip

    @commands.command()
    async def play(self, ctx, *, query: str):
        """Phát nhạc từ tên hoặc URL"""
        if not ctx.author.voice:
            return await ctx.send("Mày phải vào kênh voice trước!")

        voice_client = get(ctx.bot.voice_clients, guild=ctx.guild)

        if not voice_client or not voice_client.is_connected():
            voice_channel = ctx.author.voice.channel
            voice_client = await voice_channel.connect()

        await self.add_to_queue(ctx, query, voice_client)

    async def add_to_queue(self, ctx, query, voice_client):
        """Thêm bài hát vào hàng đợi"""
        data = await self.search_yt(query)
        if not data:
            return await ctx.send("Không tìm thấy kết quả phù hợp.")

        server_id = ctx.guild.id
        if server_id not in self.queues:
            self.queues[server_id] = []

        self.queues[server_id].append(data)
        await ctx.send(f"✅ Đã thêm **{data['title']}** vào hàng đợi.")

        if not voice_client.is_playing() and not voice_client.is_paused():
            await self.play_next(ctx, voice_client)

    async def play_next(self, ctx, voice_client):
        """Phát bài tiếp theo trong queue"""
        server_id = ctx.guild.id
        if self.queues.get(server_id):
            next_song = self.queues[server_id].pop(0)
            url = next_song["url"]

            try:
                voice_client.play(
                    FFmpegPCMAudio(url, executable="ffmpeg"),
                    after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(ctx, voice_client), self.bot.loop)
                )
                await ctx.send(f"🎵 Đang phát: **{next_song['title']}**")
            except Exception as e:
                await ctx.send(f"Lỗi khi phát nhạc: {e}")
        else:
            await ctx.send("Hết nhạc rồi, tao out đây!")
            await voice_client.disconnect()

    async def search_yt(self, query):
        """Tìm kiếm trên YouTube bằng yt-dlp"""
        ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)
        info = ytdl.extract_info(query, download=False)
        if '_type' in info and info['_type'] == 'playlist':
            return [{"title": video["title"], "url": video["url"]} for video in info["entries"]]

        return {"title": info["title"], "url": info["url"]}

    @commands.command()
    async def skip(self, ctx):
        """Vote skip bài hát hiện tại"""
        if not ctx.guild.voice_client or not ctx.guild.voice_client.is_playing():
            return await ctx.send("Hiện không có bài nào đang phát.")

        voice_client = ctx.guild.voice_client
        channel = ctx.author.voice.channel

        # Kiểm tra vote
        voters = set()
        voters.add(ctx.author.id)

        total_members = len(channel.members) - 1  # Trừ bot ra
        required_votes = max(1, int(total_members / 2))  # Cần ít nhất 50% vote

        self.votes[ctx.guild.id] = {
            "voters": voters,
            "required": required_votes
        }

        await ctx.send(f"{ctx.author.name} đã vote bỏ qua bài hát. Cần thêm {required_votes - 1} phiếu.")

        def check(reaction, user):
            return (
                reaction.message.channel == ctx.channel
                and reaction.emoji == "⏭️"
                and user in channel.members
                and user != self.bot.user
            )

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=15.0, check=check)
            self.votes[ctx.guild.id]["voters"].add(user.id)
            votes = len(self.votes[ctx.guild.id]["voters"])
            if votes >= self.votes[ctx.guild.id]["required"]:
                voice_client.stop()
                await ctx.send("⏭️ Bài hát đã bị bỏ qua.")
        except asyncio.TimeoutError:
            await ctx.send("Hết thời gian vote.")

    @commands.command()
    async def queue(self, ctx):
        """Xem danh sách chờ"""
        server_id = ctx.guild.id
        queue_list = self.queues.get(server_id, [])
        if not queue_list:
            return await ctx.send("Không có bài nào trong hàng đợi.")

        msg = "**🎶 Danh sách chờ:**\n"
        for i, song in enumerate(queue_list):
            msg += f"{i+1}. {song['title']}\n"

        await ctx.send(msg)

async def setup(bot):
    await bot.add_cog(Music(bot))
