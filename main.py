import yaml
import asyncio
import discord
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path
import sys
import os


# --- Đọc config ---
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Khởi tạo bot ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix = config["bot"]["prefix"],
    intents        = intents,
    owner_id       = config["bot"]["owner_id"]
)

# --- Kết nối MongoDB ---
db_client = AsyncIOMotorClient(config["database"]["uri"])
bot.db = db_client[config["database"]["name"]]

# --- Sự kiện on_ready: khởi tạo Javalink NodePool ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    # Tạo NodePool và kết nối đến Lavalink
    bot.lavalink = NodePool(bot)
    lava_cfg = config.get("lavalink", {})
    await bot.lavalink.create_node(
        host     = lava_cfg.get("host", "localhost"),
        port     = lava_cfg.get("port", 2207),
        password = lava_cfg.get("password", "youshallnotpass"),
        region   = lava_cfg.get("region", "asia")
    )
    print("✅ Lavalink node connected.")

# --- Bắt sự kiện raw để Javalink hoạt động ---
@bot.event
async def on_socket_raw_receive(payload):
    await bot.lavalink.listener.on_socket_raw_receive(payload)

@bot.event
async def on_socket_raw_send(payload):
    # Chỉ gửi voiceUpdate qua listener
    if payload.get("op") == "voiceUpdate":
        await bot.lavalink.listener.on_socket_raw_send(payload)

# --- Hàm chính load cogs và start bot ---
async def main():
    # Load toàn bộ *.py trong cogs (bỏ qua __init__.py)
    for file in Path("cogs").glob("*.py"):
        if file.stem.startswith("__"):
            continue
        await bot.load_extension(f"cogs.{file.stem}")
        print(f"> Loaded cog: {file.stem}")

    # Lấy token từ config hoặc biến môi trường
    token = config["bot"].get("token") or os.getenv("DISCORD_TOKEN")
    print(f"Using token: {token[:10]}…{token[-5:]}")

    if not token:
        print("❌ Bot token not found. Check config.yaml or DISCORD_TOKEN env var.")
        return

    await bot.start(token)

# --- Entry point ---
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")
