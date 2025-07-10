import discord
from discord.ext import commands
import aiohttp # Lo mantenemos para los comandos que usan otra API

# 1. Importamos nuestra nueva función de ayuda
from utils.api_helpers import get_interactive_gif

class NSFWCog(commands.Cog, name="NSFW"):
    """
    Comandos NSFW que solo se pueden usar en canales marcados como tal.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Comandos Estáticos (Ahora usan el helper) ---

    @commands.hybrid_command(name="neko_nsfw", description="Muestra una imagen NSFW de una neko.")
    @commands.is_nsfw()
    async def neko_nsfw(self, ctx: commands.Context):
        # Para imágenes estáticas, no hay un "target", así que usamos self_action_phrases
        # El texto del embed se tomará de la lista, en este caso, solo "Neko NSFW"
        await get_interactive_gif(ctx, "neko", "nsfw", self_action_phrases=["Neko NSFW"])

    @commands.hybrid_command(name="waifu_nsfw", description="Muestra una imagen NSFW de una waifu.")
    @commands.is_nsfw()
    async def waifu_nsfw(self, ctx: commands.Context):
        await get_interactive_gif(ctx, "waifu", "nsfw", self_action_phrases=["Waifu NSFW"])

    @commands.hybrid_command(name="blowjob_nsfw", description="Muestra una imagen NSFW de un blowjob.")
    @commands.is_nsfw()
    async def blowjob_nsfw(self, ctx: commands.Context):
        await get_interactive_gif(ctx, "blowjob", "nsfw", self_action_phrases=["Blowjob NSFW"])

    # --- Comandos que usan otra API (se mantienen como estaban) ---

    @commands.hybrid_command(name="boobs_nsfw", description="Muestra una imagen NSFW de pechos.")
    @commands.is_nsfw()
    async def boobs_nsfw(self, ctx: commands.Context):
        async with aiohttp.ClientSession() as session:
            async with session.get("https://nekos.best/api/v2/boobs") as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data["results"][0]["url"]
                    embed = discord.Embed(title="Boobs NSFW", color=discord.Color.light_grey())
                    embed.set_image(url=image_url)
                    await ctx.send(embed=embed)

    @commands.hybrid_command(name="pussy_nsfw", description="Muestra una imagen NSFW de una vagina.")
    @commands.is_nsfw()
    async def pussy_nsfw(self, ctx: commands.Context):
        async with aiohttp.ClientSession() as session:
            async with session.get("https://nekos.best/api/v2/pussy") as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data["results"][0]["url"]
                    embed = discord.Embed(title="Pussy NSFW", color=discord.Color.dark_magenta())
                    embed.set_image(url=image_url)
                    await ctx.send(embed=embed)

    # --- Comandos Interactivos NSFW (Ahora usan el helper y tienen todas las frases) ---

    @commands.hybrid_command(name="fuck_nsfw", description="Ten sexo con otro usuario.")
    @commands.is_nsfw()
    async def fuck_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} y {target} lo están haciendo apasionadamente.",
            "¡Las cosas se pusieron calientes! {author} está teniendo sexo con {target}.",
            "{target} está recibiendo todo el amor de {author}.",
            "Una sesión intensa entre {author} y {target}.",
            "{author} se pierde en el cuerpo de {target}."
        ]
        await get_interactive_gif(ctx, "fuck", "nsfw", target=miembro, action_templates=action_phrases)

    @commands.hybrid_command(name="cum_nsfw", description="Termina sobre otro usuario.")
    @commands.is_nsfw()
    async def cum_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} se corrió sobre {target}!",
            "{target} quedó cubierto por {author}.",
            "¡Un final feliz! {author} terminó sobre {target}.",
            "Una recompensa pegajosa de {author} para {target}.",
            "{author} deja su marca en {target}."
        ]
        await get_interactive_gif(ctx, "cum", "nsfw", target=miembro, action_templates=action_phrases)

    @commands.hybrid_command(name="handjob_nsfw", description="Hazle una paja a otro usuario.")
    @commands.is_nsfw()
    async def handjob_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} le está dando placer a {target} con sus manos.",
            "Las manos de {author} trabajan hábilmente sobre {target}.",
            "{target} disfruta de una buena paja de parte de {author}."
        ]
        # Esta categoría no está en las APIs comunes, usamos otra como placeholder
        await get_interactive_gif(ctx, "lick", "nsfw", target=miembro, action_templates=action_phrases)

    @commands.hybrid_command(name="anal_nsfw", description="Ten sexo anal con otro usuario.")
    @commands.is_nsfw()
    async def anal_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} toma a {target} por detrás.",
            "¡Por la puerta de atrás! {author} y {target} tienen una sesión anal.",
            "{target} se prepara para recibir a {author}."
        ]
        await get_interactive_gif(ctx, "anal", "nsfw", target=miembro, action_templates=action_phrases)

    @commands.hybrid_command(name="boobjob_nsfw", description="Hazle una paja con los pechos a alguien.")
    @commands.is_nsfw()
    async def boobjob_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} usa sus pechos para darle placer a {target}.",
            "{target} se pierde entre los pechos de {author}.",
            "¡Una rusa perfecta! {author} complace a {target}."
        ]
        await get_interactive_gif(ctx, "boobjob", "nsfw", target=miembro, action_templates=action_phrases)

async def setup(bot: commands.Bot):
    await bot.add_cog(NSFWCog(bot))