import asyncio
import functools
import itertools
import math
import random
import discord
import yt_dlp as youtube_dl  # Sử dụng yt-dlp thay cho youtube_dl
from async_timeout import timeout
from discord.ext import commands

# Tắt thông báo lỗi không cần thiết từ youtube_dl
youtube_dl.utils.bug_reports_message = lambda *args, **kwargs: ''


# --- Định nghĩa các Exception tùy chỉnh ---
class VoiceError(Exception):
    pass


class YTDLError(Exception):
    pass


# --- Class YTDLSource: Xử lý tải thông tin và stream nhạc từ YouTube/khác ---
class YTDLSource(discord.PCMVolumeTransformer):
    YTDL_OPTIONS = {
        'format': 'bestaudio/best',
        'extractaudio': True,
        'audioformat': 'mp3',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',  # Để tránh lỗi bind
    }

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn',
    }

    ytdl = youtube_dl.YoutubeDL(YTDL_OPTIONS)

    def __init__(self, ctx: commands.Context, source: discord.FFmpegPCMAudio, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)
        self.requester = ctx.author
        self.channel = ctx.channel
        self.data = data
        self.uploader = data.get('uploader')
        self.uploader_url = data.get('uploader_url')

        date_str = data.get('upload_date')
        if date_str and len(date_str) >= 8:
            self.upload_date = f"{date_str[6:8]}.{date_str[4:6]}.{date_str[0:4]}"
        else:
            self.upload_date = "Không xác định"

        self.title = data.get('title')
        self.thumbnail = data.get('thumbnail')
        self.description = data.get('description')
        self.duration = self.parse_duration(int(data.get('duration', 0)))
        self.tags = data.get('tags')
        self.url = data.get('webpage_url')
        self.views = data.get('view_count', 0)
        self.likes = data.get('like_count', 0)
        self.stream_url = data.get('url')

    def __str__(self):
        return f'**{self.title}** by **{self.uploader}**'

    @classmethod
    async def create_source(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()

        try:
            partial_search = functools.partial(cls.ytdl.extract_info, search, download=False, process=False)
            data = await loop.run_in_executor(None, partial_search)
        except Exception as e:
            raise YTDLError(f"Lỗi khi tìm kiếm: `{e}`")

        if data is None:
            raise YTDLError(f"Không tìm thấy bài hát nào phù hợp với `{search}`.")

        if 'entries' not in data:
            process_info = data
        else:
            process_info = None
            for entry in data['entries']:
                if entry:
                    process_info = entry
                    break
            if process_info is None:
                raise YTDLError(f"Không tìm thấy kết quả nào phù hợp với `{search}`.")

        webpage_url = process_info.get('webpage_url')
        if not webpage_url:
            raise YTDLError(f"Không tìm thấy URL hợp lệ cho `{search}`.")

        try:
            partial_process = functools.partial(cls.ytdl.extract_info, webpage_url, download=False)
            processed_info = await loop.run_in_executor(None, partial_process)
        except Exception as e:
            raise YTDLError(f"Lỗi khi tải thông tin chi tiết cho `{webpage_url}`: `{e}`")

        if processed_info is None:
            raise YTDLError(f"Không thể tải thông tin chi tiết cho `{webpage_url}`.")

        if 'entries' not in processed_info:
            info = processed_info
        else:
            info = None
            while info is None:
                try:
                    info = processed_info['entries'].pop(0)
                except IndexError:
                    raise YTDLError(f"Không thể truy xuất bất kỳ kết quả nào cho `{webpage_url}`.")

        if 'url' not in info:
            raise YTDLError(f"Không tìm thấy URL stream cho `{info.get('title', 'bài hát này')}`.")

        ffmpeg_path = ctx.bot.ffmpeg_path  # Truy cập đường dẫn ffmpeg từ bot
        return cls(ctx, discord.FFmpegPCMAudio(info['url'], executable=ffmpeg_path, **cls.FFMPEG_OPTIONS), data=info)

    @staticmethod
    def parse_duration(duration: int):
        if duration is None:
            return 'Không xác định'
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        duration_parts = []
        if days > 0:
            duration_parts.append(f'{days} ngày')
        if hours > 0:
            duration_parts.append(f'{hours} giờ')
        if minutes > 0:
            duration_parts.append(f'{minutes} phút')
        if seconds > 0:
            duration_parts.append(f'{seconds} giây')
        return ', '.join(duration_parts) if duration_parts else '0 giây'


# --- Class Song: Đại diện cho một bài hát trong hàng đợi ---
class Song:
    __slots__ = ('source', 'requester')

    def __init__(self, source: YTDLSource):
        self.source = source
        self.requester = source.requester

    def create_embed(self):
        embed = (discord.Embed(title='Đang phát 🎶',
                               description=f'```css\n{self.source.title}\n```',
                               color=discord.Color.blurple())
                 .add_field(name='Thời lượng', value=self.source.duration, inline=True)
                 .add_field(name='Yêu cầu bởi', value=self.requester.mention, inline=True)
                 .add_field(name='Uploader', value=f'[{self.source.uploader}]({self.source.uploader_url})', inline=True)
                 .set_thumbnail(url=self.source.thumbnail))

        footer_text_parts = []
        if self.source.views is not None:
            footer_text_parts.append(f'Lượt xem: {self.source.views:,}')
        if self.source.likes is not None:
            footer_text_parts.append(f'Lượt thích: {self.source.likes:,}')
        if footer_text_parts:
            embed.set_footer(text=' | '.join(footer_text_parts))
        return embed


# --- Class SongQueue: Hàng đợi bài hát ---
class SongQueue(asyncio.Queue):
    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(itertools.islice(self._queue, item.start, item.stop, item.step))
        else:
            return self._queue[item]

    def __iter__(self):
        return self._queue.__iter__()

    def __len__(self):
        return self.qsize()

    def clear(self):
        self._queue.clear()

    def shuffle(self):
        random.shuffle(self._queue)

    def remove(self, index: int):
        if 0 <= index < len(self._queue):
            del self._queue[index]
            return True
        return False


# --- Class VoiceState: Quản lý trạng thái voice connection và phát nhạc ---
class VoiceState:
    def __init__(self, bot: commands.Bot, ctx: commands.Context):
        self.bot = bot
        self._ctx = ctx
        self.current = None
        self.voice = None
        self.next = asyncio.Event()
        self.songs = SongQueue()
        self._loop = False
        self._volume = 0.5  # Mặc định âm lượng 50%
        self.skip_votes = set()
        self.audio_player = bot.loop.create_task(self.audio_player_task())

    def __del__(self):
        if self.audio_player and not self.audio_player.done():
            self.audio_player.cancel()

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value: float):
        self._volume = value
        if self.voice and self.voice.source:
            self.voice.source.volume = value

    @property
    def is_playing(self):
        return self.voice and self.current

    async def audio_player_task(self):
        while True:
            self.next.clear()
            if not self.loop:
                try:
                    async with timeout(300):  # 5 phút timeout
                        self.current = await self.songs.get()
                except asyncio.TimeoutError:
                    await self._ctx.send("Không có nhạc trong 5 phút, tôi tự động rời kênh.")
                    self.bot.loop.create_task(self.stop())
                    return

            if not self.voice or not self.voice.is_connected():
                print("Voice client không còn hoạt động, dừng audio_player_task.")
                break

            self.current.source.volume = self._volume
            self.voice.play(self.current.source, after=self.play_next_song)
            await self.current.source.channel.send(embed=self.current.create_embed())
            await self.next.wait()

    def play_next_song(self, error=None):
        if error:
            print(f'Lỗi phát nhạc: {error}')
            asyncio.run_coroutine_threadsafe(self._ctx.send(f'Đã xảy ra lỗi khi phát nhạc: {error}'), self.bot.loop)
        self.next.set()

    def skip(self):
        self.skip_votes.clear()
        if self.is_playing:
            self.voice.stop()

    async def stop(self):
        self.songs.clear()
        if self.voice:
            await self.voice.disconnect()
        self.voice = None
        self.current = None
        if self.audio_player and not self.audio_player.done():
            self.audio_player.cancel()


# --- Helper function for checks ---
async def is_in_voice_channel(ctx: commands.Context):
    if not ctx.author.voice or not ctx.author.voice.channel:
        raise commands.CommandError('Mày không ở trong kênh thoại à?')
    return True


# --- Class Music (Cog) ---
class music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, ctx: commands.Context):
        state = self.voice_states.get(ctx.guild.id)
        if not state:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state
        return state

    def cog_unload(self):
        for state in self.voice_states.values():
            self.bot.loop.create_task(state.stop())

    def cog_check(self, ctx: commands.Context):
        if not ctx.guild:
            raise commands.NoPrivateMessage('Mày nhắn riêng thì Tao không chơi.')
        return True

    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandInvokeError):
            print(f"Lỗi trong lệnh '{ctx.command.qualified_name}':")
            import traceback
            traceback.print_exception(type(error.original), error.original, error.original.__traceback__)
            await ctx.send(f'Tao gặp lỗi rồi thằng ml: {error.original}')
        else:
            await ctx.send(f'Tao gặp lỗi rồi thằng ml: {error}')

    # --- Các lệnh của Music Bot ---
    @commands.command(name='join', invoke_without_subcommand=True)
    @commands.check(is_in_voice_channel)
    async def _join(self, ctx: commands.Context):
        destination = ctx.author.voice.channel
        if ctx.voice_state.voice:
            if ctx.voice_state.voice.channel != destination:
                await ctx.voice_state.voice.move_to(destination)
                await ctx.send(f'Đã chuyển sang kênh thoại: **{destination}**')
            else:
                await ctx.send('Tao đã ở trong kênh của mày rồi, đồ đần.')
        else:
            ctx.voice_state.voice = await destination.connect()
            await ctx.send(f"Tao đã vào kênh: **{destination}** rồi, con ml.")

    @commands.command(name='summon')
    @commands.has_permissions(manage_guild=True)
    async def _summon(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        if not channel:
            if not ctx.author.voice or not ctx.author.voice.channel:
                raise commands.CommandError('Mày không ở trong kênh thoại nào cả để tao summon đâu.')
            channel = ctx.author.voice.channel

        if ctx.voice_state.voice:
            if ctx.voice_state.voice.channel != channel:
                await ctx.voice_state.voice.move_to(channel)
                await ctx.send(f'Đã chuyển sang kênh thoại: **{channel}**')
            else:
                await ctx.send('Tao đã ở trong kênh thoại đó rồi.')
        else:
            ctx.voice_state.voice = await channel.connect()
            await ctx.send(f'Đã vào kênh thoại: **{channel}**')

    @commands.command(name='leave', aliases=['disconnect', 'dc'])
    async def _leave(self, ctx: commands.Context):
        if not ctx.voice_state.voice:
            return await ctx.send('Tao chưa vào kênh nào cả, đồ đần.')

        if ctx.voice_state.audio_player and not ctx.voice_state.audio_player.done():
            ctx.voice_state.audio_player.cancel()

        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]
        await ctx.message.add_reaction('✅')
        await ctx.send("Tao out đây, bye mẹ mày.")

    @commands.command(name='volume', aliases=['vol'])
    async def _volume(self, ctx: commands.Context, *, volume: int):
        if not ctx.voice_state.is_playing:
            return await ctx.send('Hiện tại không có bài hát nào đang phát.')

        if not 0 <= volume <= 100:
            return await ctx.send('Mày tưởng volume là muốn bao nhiêu cũng được à? 0 đến 100 thôi.')

        ctx.voice_state.volume = volume / 100
        await ctx.send(f'Tao đã chỉnh volume lên **{volume}%** rồi, hài lòng chưa con ml?')

    @commands.command(name='now', aliases=['np', 'current', 'playing'])
    async def _now(self, ctx: commands.Context):
        if not ctx.voice_state.is_playing:
            return await ctx.send('Hiện tại không có bài hát nào đang phát.')
        await ctx.send(embed=ctx.voice_state.current.create_embed())
        await ctx.send("Tao đang phát bài này đó, nghe kỹ vào.")

    @commands.command(name='pause', aliases=['pa'])
    async def _pause(self, ctx: commands.Context):
        if ctx.voice_state.is_playing and ctx.voice_state.voice.is_playing():
            ctx.voice_state.voice.pause()
            await ctx.message.add_reaction('⏸️')
            await ctx.send("Tao pause lại đây để mày nghỉ hít thở.")
        else:
            await ctx.send("Không có bài hát nào để tạm dừng hoặc đã tạm dừng rồi.")

    @commands.command(name='resume', aliases=['re'])
    async def _resume(self, ctx: commands.Context):
        if ctx.voice_state.is_playing and ctx.voice_state.voice.is_paused():
            ctx.voice_state.voice.resume()
            await ctx.message.add_reaction('▶️')
            await ctx.send("Tao tiếp tục phát đây, đừng có ngắt giữa chừng nữa.")
        else:
            await ctx.send("Không có bài hát nào để tiếp tục hoặc đang phát rồi.")

    @commands.command(name='stop', aliases=['close'])
    async def _stop(self, ctx: commands.Context):
        if not ctx.voice_state.voice:
            return await ctx.send('Tao chưa vào kênh nào cả để dừng.')

        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]
        await ctx.message.add_reaction('⏹️')
        await ctx.send("Tao tắt hết bài hát đi rồi, khỏi nghe nữa.")

    @commands.command(name='skip', aliases=['sk'])
    async def _skip(self, ctx: commands.Context):
        if not ctx.voice_state.is_playing:
            return await ctx.send('Hiện tại không có bài nào đang phát.')

        voter = ctx.author

        if voter == ctx.voice_state.current.requester:
            await ctx.message.add_reaction('⏭️')
            ctx.voice_state.skip()
            return await ctx.send("Bài này bị skip vì thằng request nó ngu vl.")

        if voter.id in ctx.voice_state.skip_votes:
            return await ctx.send('Mày đã vote skip rồi mà còn vote nữa à?')

        ctx.voice_state.skip_votes.add(voter.id)

        members_in_channel = [m for m in ctx.voice_state.voice.channel.members if not m.bot and m.voice]
        if len(members_in_channel) <= 1:
            await ctx.message.add_reaction('⏭️')
            ctx.voice_state.skip()
            return await ctx.send("Không có ai khác trong kênh, tự động bỏ qua.")

        required_votes = math.ceil(len(members_in_channel) / 2)
        if len(ctx.voice_state.skip_votes) >= required_votes:
            await ctx.message.add_reaction('⏭️')
            ctx.voice_state.skip()
            await ctx.send(f'Đủ {required_votes} phiếu, đã bỏ qua bài hát.')
        else:
            await ctx.send(f'Có thêm 1 vote skip, hiện tại {len(ctx.voice_state.skip_votes)}/{required_votes} vote.')

    @commands.command(name='queue', aliases=['q', 'playlist'])
    async def _queue(self, ctx: commands.Context, *, page: int = 1):
        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Hàng đợi trống, mày không biết add bài à?')

        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs) / items_per_page)
        if page > pages or page <= 0:
            return await ctx.send(f'Trang không hợp lệ. Có {pages} trang.')

        start = (page - 1) * items_per_page
        end = start + items_per_page

        current_song_info = ""
        if ctx.voice_state.current:
            status = "Đang phát" if not ctx.voice_state.loop else "Đang lặp lại"
            current_song_info = f'**{status}:** [{ctx.voice_state.current.source.title}]({ctx.voice_state.current.source.url})\n'

        queue_display = ''
        for i, song in enumerate(ctx.voice_state.songs[start:end], start=start):
            queue_display += f'`{i + 1}.` [{song.source.title}]({song.source.url})\n'

        embed = (discord.Embed(title='Hàng đợi 🎼',
                               description=f'{current_song_info}**{len(ctx.voice_state.songs)} bài hát trong hàng đợi:**\n{queue_display}',
                               color=discord.Color.dark_teal())
                 .set_footer(text=f'Trang {page}/{pages}'))
        await ctx.send(embed=embed)
        await ctx.send("Đây là hàng đợi của mày, tự xem đi.")

    @commands.command(name='shuffle')
    async def _shuffle(self, ctx: commands.Context):
        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Hàng đợi trống, mày không biết xáo trộn à?')
        ctx.voice_state.songs.shuffle()
        await ctx.message.add_reaction('✅')
        await ctx.send('Đã xáo trộn hàng đợi.')

    @commands.command(name='remove', aliases=['rm'])
    async def _remove(self, ctx: commands.Context, index: int):
        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Hàng đợi trống, mày không có gì để xóa.')

        if not (1 <= index <= len(ctx.voice_state.songs)):
            return await ctx.send(f'Số thứ tự bài hát không hợp lệ. Chỉ có từ 1 đến {len(ctx.voice_state.songs)}.')

        if ctx.voice_state.songs.remove(index - 1):
            await ctx.message.add_reaction('✅')
            await ctx.send(f'Đã xóa bài hát số {index} khỏi hàng đợi.')
        else:
            await ctx.send('Không thể xóa bài hát.')

    @commands.command(name='loop')
    async def _loop(self, ctx: commands.Context):
        if not ctx.voice_state.is_playing:
            return await ctx.send('Không có bài nào đang phát.')
        ctx.voice_state.loop = not ctx.voice_state.loop
        status = 'bật' if ctx.voice_state.loop else 'tắt'
        await ctx.message.add_reaction('✅')
        await ctx.send(f'Chế độ lặp lại đã được **{status}**.')

    @commands.command(name='play', aliases=['p'])
    @commands.check(is_in_voice_channel)
    async def _play(self, ctx: commands.Context, *, search: str):
        if not ctx.voice_state.voice:
            destination = ctx.author.voice.channel
            try:
                ctx.voice_state.voice = await destination.connect()
                await ctx.send(f"Tao đã vào kênh: **{destination}** rồi, con ml.")
            except Exception as e:
                return await ctx.send(f"Không thể kết nối đến kênh thoại: {e}")
            await asyncio.sleep(0.5)

        async with ctx.typing():
            try:
                source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop)
            except YTDLError as e:
                return await ctx.send(f'Tao không tìm được bài "{search}", mày gõ đúng tên coi. Lỗi: {e}')
            except Exception as e:
                import traceback
                traceback.print_exc()
                return await ctx.send(f'Đã xảy ra lỗi không mong muốn khi tìm bài hát: {e}')
            else:
                song = Song(source)
                await ctx.voice_state.songs.put(song)
                await ctx.send(f'Tao đã cho "{source.title}" vào hàng đợi rồi, chờ đi.')


# Hàm setup cho cog, phải là async
async def setup(bot):
    await bot.add_cog(music(bot))
