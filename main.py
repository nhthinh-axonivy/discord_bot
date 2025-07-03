import yaml
import asyncio
import discord
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path
import os
import traceback

# --- Đọc config ---
try:
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    print("❌ Lỗi nghiêm trọng: File config.yaml không tồn tại. Vui lòng tạo file này với cấu hình cần thiết.")
    exit(1)
except yaml.YAMLError as e:
    print(f"❌ Lỗi nghiêm trọng: Không thể đọc config.yaml. Lỗi cú pháp YAML: {e}")
    exit(1)

class MusicBot(commands.Bot):
    def __init__(self):
        # Định nghĩa Intents cần thiết cho bot Discord
        intents = discord.Intents.default()
        intents.members = True        # Cần thiết để truy cập thông tin thành viên
        intents.message_content = True  # Cần thiết để đọc nội dung tin nhắn (cho lệnh)
        intents.voice_states = True     # Cần thiết để bot tham gia/rời kênh thoại và kiểm soát trạng thái voice

        super().__init__(
            command_prefix=config["bot"]["prefix"], # Tiền tố lệnh từ config.yaml
            intents=intents,
            owner_id=config["bot"]["owner_id"]      # ID chủ bot từ config.yaml
        )
        self.config = config # Lưu config để các phần khác của bot có thể truy cập
        self.db = None       # Biến để lưu trữ kết nối MongoDB
        
        # Loại bỏ self.music_queues ở đây. Music Cog sẽ tự quản lý trạng thái voice.
        # self.music_queues = {} 
        
        # Lấy đường dẫn FFmpeg từ config, mặc định là "ffmpeg" nếu không tìm thấy
        self.ffmpeg_path = self.config.get("ffmpeg", {}).get("path", "ffmpeg") 

    async def setup_hook(self):
        """
        Phương thức này được gọi ngay sau khi bot được khởi tạo nhưng trước khi bot đăng nhập.
        Là nơi lý tưởng để thiết lập các thành phần cần thiết trước khi cogs được tải.
        """
        # --- Kết nối MongoDB ---
        try:
            db_client = AsyncIOMotorClient(self.config["database"]["uri"])
            self.db = db_client[self.config["database"]["name"]]
            print("✅ Đã kết nối MongoDB.")
        except Exception as e:
            print(f"❌ Lỗi: Không thể kết nối MongoDB: {e}. Vui lòng kiểm tra URI MongoDB trong config.yaml.")
            # Không thoát bot ngay để bot vẫn có thể chạy mà không có DB nếu cần, nhưng cảnh báo
            # exit(1) 

        # --- Tải toàn bộ cog trong thư mục cogs ---
        cogs_path = Path("cogs")
        if not cogs_path.is_dir():
            print(f"❌ Lỗi: Thư mục '{cogs_path}' không tồn tại. Vui lòng tạo thư mục 'cogs' và đặt các file cog vào đó.")
            return

        for file in cogs_path.glob("*.py"): # Duyệt qua tất cả các file .py trong thư mục cogs
            if file.name.startswith("__"): # Bỏ qua các file như __init__.py
                continue
            cog_name = f"cogs.{file.stem}" # Tạo tên cog dạng package (e.g., "cogs.music")
            try:
                await self.load_extension(cog_name) # Tải cog
                print(f"> Đã tải cog: {file.stem}")
            except Exception as e:
                print(f"❌ Không thể tải cog {file.stem}: {e}")
                traceback.print_exc() # In chi tiết traceback cho lỗi tải cog để dễ debug

    async def on_ready(self):
        """
        Được gọi khi bot đã sẵn sàng và đã đăng nhập vào Discord.
        """
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

    async def on_voice_state_update(self, member, before, after):
        """
        Xử lý khi trạng thái voice của thành viên thay đổi.
        Nếu bot bị kick khỏi kênh thoại, hãy ngắt kết nối và xóa hàng đợi.
        """
        # Kiểm tra nếu thành viên là bot và nó rời kênh thoại (before.channel tồn tại, after.channel không)
        if member == self.user and before.channel and not after.channel:
            guild_id = before.channel.guild.id
            # Truy cập cog 'music' để gọi phương thức stop của VoiceState
            music_cog = self.get_cog('music') # Lấy instance của Music Cog
            if music_cog and guild_id in music_cog.voice_states:
                voice_state = music_cog.voice_states[guild_id]
                await voice_state.stop() # Gọi phương thức stop của VoiceState để dừng nhạc và dọn dẹp
                del music_cog.voice_states[guild_id] # Xóa state khỏi dictionary của Music Cog
                print(f"Bot đã bị ngắt kết nối khỏi kênh thoại và hàng đợi đã bị xóa trong guild {guild_id}.")


    async def on_command_error(self, ctx, error):
        """
        Bộ xử lý lỗi tập trung cho tất cả các lệnh của bot.
        """
        if isinstance(error, commands.CommandNotFound):
            return # Bỏ qua lỗi khi lệnh không tồn tại
        elif isinstance(error, commands.MissingRequiredArgument):
            # Lỗi khi thiếu tham số cần thiết cho lệnh
            await ctx.send(f"❌ Thiếu tham số: `{error.param.name}`. Ví dụ: `!{ctx.command.name} {ctx.command.signature.replace('ctx, ', '')}`")
        elif isinstance(error, commands.NoPrivateMessage):
            # Lỗi khi lệnh được sử dụng trong tin nhắn riêng tư thay vì server
            await ctx.send("❌ Lệnh này chỉ hoạt động trong server.")
        elif isinstance(error, commands.BotMissingPermissions):
            # Lỗi khi bot thiếu quyền cần thiết để thực hiện lệnh
            perms = [f"`{p.replace('_', ' ').title()}`" for p in error.missing_permissions]
            await ctx.send(f"❌ Bot thiếu quyền: {', '.join(perms)} cần thiết để thực hiện lệnh này.")
        elif isinstance(error, commands.MissingPermissions):
            # Lỗi khi người dùng thiếu quyền để sử dụng lệnh
            perms = [f"`{p.replace('_', ' ').title()}`" for p in error.missing_permissions]
            await ctx.send(f"❌ Bạn thiếu quyền: {', '.join(perms)} để sử dụng lệnh này.")
        elif isinstance(error, commands.NotOwner):
            # Lỗi khi lệnh chỉ dành cho chủ bot nhưng người dùng không phải chủ bot
            await ctx.send("❌ Bạn không phải là chủ bot.")
        elif isinstance(error, commands.CheckFailure):
            # Lỗi khi một check tùy chỉnh không được đáp ứng
            # Đây có thể là nơi bạn muốn in ra lỗi gốc từ check để có thông tin cụ thể hơn
            # Ví dụ: await ctx.send(f"❌ {error.args[0]}") nếu check raise một CommandError với thông báo
            await ctx.send(f"❌ Bạn không có quyền sử dụng lệnh này hoặc điều kiện không được đáp ứng. Lỗi: `{error}`")
        elif isinstance(error, commands.CommandInvokeError):
            # Lỗi xảy ra trong quá trình thực thi lệnh (lỗi bên trong code lệnh)
            original_error = error.original
            await ctx.send(f"❌ Có lỗi khi thực thi lệnh: `{original_error}`")
            print(f"Lỗi CommandInvokeError trong lệnh {ctx.command.qualified_name}: {type(original_error).__name__}: {original_error}")
            traceback.print_exc() # In chi tiết traceback để debug
        else:
            # Các lỗi không xác định khác
            await ctx.send(f"❌ Có lỗi không mong muốn xảy ra: `{error}`")
            print(f"Lỗi trong lệnh {ctx.command} ({ctx.command.qualified_name}): {type(error).__name__}: {error}")
            traceback.print_exc() # In chi tiết traceback

# --- Hàm chính để khởi động bot ---
async def main():
    bot = MusicBot()
    
    token = bot.config["bot"].get("token") or os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Lỗi nghiêm trọng: Bot token không tìm thấy. Vui lòng kiểm tra config.yaml hoặc biến môi trường DISCORD_TOKEN.")
        return

    print(f"Đang cố gắng đăng nhập với token: {token[:10]}...{token[-5:]}")
    try:
        await bot.start(token)
    except discord.LoginFailure:
        print("❌ Lỗi nghiêm trọng: Token bot không hợp lệ. Vui lòng kiểm tra lại token trong config.yaml.")
    except Exception as e:
        print(f"❌ Lỗi không mong muốn khi khởi động bot: {e}")
        traceback.print_exc()

# --- Entry point của chương trình (khi file được chạy trực tiếp) ---
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot đã dừng bởi người dùng (Ctrl+C).")
    except Exception as e:
        print(f"Lỗi không mong muốn trong quá trình chạy chính: {e}")
        traceback.print_exc()