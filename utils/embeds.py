import discord

def create_embed(title, description, color=0xFF0000):
    return discord.Embed(title=title, description=description, color=color)
