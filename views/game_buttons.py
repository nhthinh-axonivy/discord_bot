import discord
from discord import ui
import random

class DiceGameView(ui.View):
    def __init__(self, bot, bet, user):
        super().__init__(timeout=60)
        self.bot = bot
        self.bet = bet
        self.user = user

    @ui.button(label="🎲 ROLL", style=discord.ButtonStyle.primary)
    async def roll(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("Không phải mày chơi!", ephemeral=True)

        user_dice = random.randint(1, 6)
        bot_dice = random.randint(1, 6)

        if user_dice > bot_dice:
            await self.bot.db.users.update_one(
                {"user_id": self.user.id},
                {"$inc": {"money": self.bet * 2}},
                upsert=True
            )
            result = f"Người chơi: {user_dice}, Bot: {bot_dice} - **Mày thắng!**"
        elif user_dice < bot_dice:
            await self.bot.db.users.update_one(
                {"user_id": self.user.id},
                {"$inc": {"money": -self.bet}},
                upsert=True
            )
            result = f"Người chơi: {user_dice}, Bot: {bot_dice} - **Mày thua!**"
        else:
            result = "Hòa! Không ai mất tiền."

        await interaction.response.edit_message(content=result, view=None)

    @ui.button(label="❌ Hủy", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.message.delete()
