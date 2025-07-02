import discord
from discord import ui

class MusicButtons(ui.View):
    def __init__(self, bot, voice_client):
        super().__init__(timeout=None)
        self.bot = bot
        self.voice_client = voice_client

    @ui.button(label="⏮️", style=discord.ButtonStyle.grey)
    async def previous(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("Chức năng chưa hỗ trợ.", ephemeral=True)

    @ui.button(label="⏸️", style=discord.ButtonStyle.red)
    async def pause(self, interaction: discord.Interaction, button: ui.Button):
        if self.voice_client.is_paused():
            self.voice_client.resume()
            await interaction.response.edit_message(content="Tiếp tục phát nhạc.", view=self)
        else:
            self.voice_client.pause()
            await interaction.response.edit_message(content="Đã tạm dừng.", view=self)

    @ui.button(label="⏭️", style=discord.ButtonStyle.green)
    async def skip(self, interaction: discord.Interaction, button: ui.Button):
        if self.voice_client.is_playing():
            self.voice_client.stop()
            await interaction.response.edit_message(content="Bỏ qua bài hát thành công!", view=self)
        else:
            await interaction.response.send_message("Không có bài nào đang phát.", ephemeral=True)
