import discord
from discord.ext import commands
import random

# Importamos nuestra función de ayuda centralizada
from utils.api_helpers import get_interactive_gif

class NSFWCog(commands.Cog, name="NSFW"):
    """
    Comandos NSFW que solo se pueden usar en canales marcados como tal.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Comandos Estáticos ---
    # Estos existen en la API waifu.pics
    @commands.hybrid_command(name="neko_nsfw", description="Muestra una imagen NSFW de una neko.")
    @commands.is_nsfw()
    async def neko_nsfw(self, ctx: commands.Context):
        await get_interactive_gif(ctx, "neko", "nsfw", self_action_phrases=["Neko NSFW"])

    @commands.hybrid_command(name="waifu_nsfw", description="Muestra una imagen NSFW de una waifu.")
    @commands.is_nsfw()
    async def waifu_nsfw(self, ctx: commands.Context):
        await get_interactive_gif(ctx, "waifu", "nsfw", self_action_phrases=["Waifu NSFW"])

    @commands.hybrid_command(name="blowjob_nsfw", description="Muestra una imagen NSFW de un blowjob.")
    @commands.is_nsfw()
    async def blowjob_nsfw(self, ctx: commands.Context):
        await get_interactive_gif(ctx, "blowjob", "nsfw", self_action_phrases=["Blowjob NSFW"])

    # --- Comandos con categoría de REEMPLAZO ---
    # Las siguientes categorías no existen en waifu.pics, así que usamos 'waifu' como reemplazo para que el comando no falle.
    @commands.hybrid_command(name="boobs_nsfw", description="Muestra una imagen NSFW de pechos.")
    @commands.is_nsfw()
    async def boobs_nsfw(self, ctx: commands.Context):
        await get_interactive_gif(ctx, "waifu", "nsfw", self_action_phrases=["Boobs NSFW"]) # Reemplazo

    @commands.hybrid_command(name="pussy_nsfw", description="Muestra una imagen NSFW de una vagina.")
    @commands.is_nsfw()
    async def pussy_nsfw(self, ctx: commands.Context):
        await get_interactive_gif(ctx, "waifu", "nsfw", self_action_phrases=["Pussy NSFW"]) # Reemplazo

    # --- Comandos Interactivos NSFW ---

    @commands.hybrid_command(name="fuck_nsfw", description="Ten sexo con otro usuario.")
    @commands.is_nsfw()
    async def fuck_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} y {target} lo están haciendo apasionadamente.",
            "¡Las cosas se pusieron calientes! {author} está teniendo sexo con {target}.",
            "{target} está recibiendo todo el amor de {author}.",
        ]
        # waifu.pics tiene la categoría 'trap' que puede servir como un reemplazo visual genérico.
        await get_interactive_gif(ctx, "trap", "nsfw", target=miembro, action_templates=action_phrases)

    @commands.hybrid_command(name="cum_nsfw", description="Termina sobre otro usuario.")
    @commands.is_nsfw()
    async def cum_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} se corrió sobre {target}!",
            "{target} quedó cubierto por {author}.",
            "¡Un final feliz! {author} terminó sobre {target}.",
        ]
        # Usamos 'waifu' como reemplazo
        await get_interactive_gif(ctx, "waifu", "nsfw", target=miembro, action_templates=action_phrases)

    @commands.hybrid_command(name="handjob_nsfw", description="Hazle una paja a otro usuario.")
    @commands.is_nsfw()
    async def handjob_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} le está dando placer a {target} con sus manos.",
            "Las manos de {author} trabajan hábilmente sobre {target}.",
        ]
        # Usamos 'blowjob' como el reemplazo visual más cercano.
        await get_interactive_gif(ctx, "blowjob", "nsfw", target=miembro, action_templates=action_phrases)

    @commands.hybrid_command(name="anal_nsfw", description="Ten sexo anal con otro usuario.")
    @commands.is_nsfw()
    async def anal_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} toma a {target} por detrás.",
            "¡Por la puerta de atrás! {author} y {target} tienen una sesión anal.",
        ]
        # Usamos 'trap' como reemplazo visual.
        await get_interactive_gif(ctx, "trap", "nsfw", target=miembro, action_templates=action_phrases)

    @commands.hybrid_command(name="boobjob_nsfw", description="Hazle una paja con los pechos a alguien.")
    @commands.is_nsfw()
    async def boobjob_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} usa sus pechos para darle placer a {target}.",
            "{target} se pierde entre los pechos de {author}.",
        ]
        # Usamos 'waifu' como reemplazo.
        await get_interactive_gif(ctx, "waifu", "nsfw", target=miembro, action_templates=action_phrases)

async def setup(bot: commands.Bot):
    await bot.add_cog(NSFWCog(bot))