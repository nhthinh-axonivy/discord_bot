import asyncio
import discord
import yt_dlp

class MusicPlayer:
    def __init__(self, bot, guild_id, ffmpeg_path):
        self.bot = bot
        self.guild_id = guild_id
        self.ffmpeg_path = ffmpeg_path # Đường dẫn đến FFmpeg từ config
        self.queue = asyncio.Queue()
        self.current_track = None
        self.voice_client = None
        self.text_channel = None # Kênh văn bản để gửi thông báo
        self.loop_track = False # Trạng thái lặp lại bài hát hiện tại
        self.loop_queue = False # Trạng thái lặp lại toàn bộ hàng đợi
        self.playing = False # Trạng thái đang phát nhạc

        self.YDL_OPTIONS = {
            'format': 'bestaudio/best',
            'restrictfilenames': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'ignoreerrors': True,
            'logtostderr': False,
            'quiet': True,
            'no_warnings': True,
            'default_search': 'ytsearch',
            'source_address': '0.0.0.0', # Để tránh lỗi IPv6 khi tìm kiếm
            'extractor_args': {
                'youtube': {
                    'skip_dash_manifest': ['--skip-dash-manifest']
                }
            }
        }
        self.FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn' # Không xử lý video
        }

    async def connect(self, channel: discord.VoiceChannel):
        if self.voice_client:
            if self.voice_client.channel.id != channel.id:
                await self.voice_client.move_to(channel)
        else:
            self.voice_client = await channel.connect()
        return self.voice_client

    def is_playing(self):
        return self.voice_client and self.voice_client.is_playing()

    def is_paused(self):
        return self.voice_client and self.voice_client.is_paused()
        
    def stop(self):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
        self.playing = False
        self.current_track = None

    async def disconnect(self):
        self.stop()
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None
        self.queue = asyncio.Queue() # Xóa hàng đợi khi ngắt kết nối
        self.text_channel = None
        self.loop_track = False
        self.loop_queue = False
        self.playing = False

    async def get_track_info(self, query: str):
        try:
            # yt-dlp có thể cần đường dẫn đến ffmpeg nếu không có trong PATH hệ thống
            ydl_opts = self.YDL_OPTIONS.copy()
            if self.ffmpeg_path and self.ffmpeg_path != "ffmpeg":
                # Nếu ffmpeg_path được chỉ định rõ ràng, yt-dlp sẽ sử dụng nó
                # Mặc định yt-dlp sẽ tìm ffmpeg trong PATH
                pass 

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, query, download=False)
                if 'entries' in info:
                    info = info['entries'][0] # Lấy kết quả đầu tiên nếu là playlist/search
                return info
        except Exception as e:
            print(f"Lỗi khi lấy thông tin track: {e}")
            return None

    async def play_next_track(self):
        if self.is_playing():
            return

        if self.loop_track and self.current_track:
            track_to_play = self.current_track
        elif not self.queue.empty():
            track_to_play = self.queue.get_nowait()
            self.current_track = track_to_play
        elif self.loop_queue and self.current_track: # Nếu lặp queue và đã phát hết các bài khác
            # Đẩy bài vừa phát vào cuối hàng đợi để lặp lại
            await self.queue.put(self.current_track) 
            # Sau đó lấy bài tiếp theo (bài vừa được put vào)
            track_to_play = self.queue.get_nowait()
            self.current_track = track_to_play
        else: # Hàng đợi rỗng và không có chế độ lặp
            self.current_track = None
            self.playing = False
            if self.text_channel:
                await self.text_channel.send("🎶 Đã phát hết hàng đợi.")
            return

        try:
            # Sử dụng executable của FFmpeg từ đường dẫn được cấu hình
            source = discord.FFmpegPCM(track_to_play['url'], executable=self.ffmpeg_path, **self.FFMPEG_OPTIONS)
            self.voice_client.play(source, after=lambda e: self.bot.loop.call_soon_threadsafe(self.after_play_callback, e))
            self.playing = True
            
            if self.text_channel:
                embed = discord.Embed(
                    title="🎵 Đang phát:",
                    description=f"[{track_to_play['title']}]({track_to_play['webpage_url']})",
                    color=discord.Color.green()
                )
                if track_to_play.get('thumbnail'):
                    embed.set_thumbnail(url=track_to_play['thumbnail'])
                
                loop_status = []
                if self.loop_track:
                    loop_status.append("Bài hát: 🔁")
                if self.loop_queue:
                    loop_status.append("Hàng đợi: 🔂")
                if loop_status:
                    embed.set_footer(text=" | ".join(loop_status))
                
                await self.text_channel.send(embed=embed)

        except Exception as e:
            print(f"Lỗi khi phát nhạc: {e}")
            if self.text_channel:
                await self.text_channel.send(f"❌ Lỗi khi phát nhạc: `{e}`. Bỏ qua bài này.")
            self.after_play_callback(e)

    def after_play_callback(self, error):
        if error:
            print(f"Lỗi trong quá trình phát: {error}")
        
        self.playing = False

        if self.loop_track and self.current_track:
            self.bot.loop.create_task(self.play_next_track())
            return
        
        # Nếu đang lặp hàng đợi và bài hát vừa phát không phải là bài cuối cùng
        # Hoặc là bài cuối cùng nhưng vẫn muốn lặp lại.
        if self.loop_queue and self.current_track and self.queue.empty():
            self.bot.loop.create_task(self.queue.put(self.current_track)) # Đẩy bài vừa phát vào cuối queue

        # Bắt đầu phát bài tiếp theo
        self.bot.loop.create_task(self.play_next_track())
