import discord
from discord.ext import commands
import random

# Importamos nuestra función de ayuda centralizada
from utils.api_helpers import get_interactive_gif

class NSFWCog(commands.Cog, name="NSFW"):
    """
    Comandos NSFW que solo se pueden usar en canales marcados como tal.
    Usa la API de Nekos.best
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Comandos Estáticos ---

    @commands.hybrid_command(name="neko_nsfw", description="Muestra una imagen NSFW de una neko.")
    @commands.is_nsfw()
    async def neko_nsfw(self, ctx: commands.Context):
        # La categoría en la API es 'neko'
        await get_interactive_gif(ctx, "neko", "nsfw", self_action_phrases=["Neko NSFW"])

    @commands.hybrid_command(name="waifu_nsfw", description="Muestra una imagen NSFW de una waifu.")
    @commands.is_nsfw()
    async def waifu_nsfw(self, ctx: commands.Context):
        # La categoría en la API es 'waifu'
        await get_interactive_gif(ctx, "waifu", "nsfw", self_action_phrases=["Waifu NSFW"])

    @commands.hybrid_command(name="blowjob_nsfw", description="Muestra una imagen NSFW de un blowjob.")
    @commands.is_nsfw()
    async def blowjob_nsfw(self, ctx: commands.Context):
        # La categoría en la API es 'blowjob'
        await get_interactive_gif(ctx, "blowjob", "nsfw", self_action_phrases=["Blowjob NSFW"])

    @commands.hybrid_command(name="boobs_nsfw", description="Muestra una imagen NSFW de pechos.")
    @commands.is_nsfw()
    async def boobs_nsfw(self, ctx: commands.Context):
        # La categoría en la API es 'boobs'
        await get_interactive_gif(ctx, "boobs", "nsfw", self_action_phrases=["Boobs NSFW"])

    @commands.hybrid_command(name="pussy_nsfw", description="Muestra una imagen NSFW de una vagina.")
    @commands.is_nsfw()
    async def pussy_nsfw(self, ctx: commands.Context):
        # La categoría en la API es 'pussy'
        await get_interactive_gif(ctx, "pussy", "nsfw", self_action_phrases=["Pussy NSFW"])

    # --- Comandos Interactivos NSFW ---

    @commands.hybrid_command(name="fuck_nsfw", description="Ten sexo con otro usuario.")
    @commands.is_nsfw()
    async def fuck_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} y {target} lo están haciendo apasionadamente.",
            "¡Las cosas se pusieron calientes! {author} está teniendo sexo con {target}.",
            "{target} está recibiendo todo el amor de {author}.",
            "{author} y {target} están enredados en un acto de pura pasión.",
            "La habitación se llena de gemidos mientras {author} se une a {target}.",
            "{target} se entrega por completo al placer que {author} le está dando.",
            "Una conexión íntima y salvaje entre {author} y {target}.",
        ]
        # La categoría en la API es 'fuck'
        await get_interactive_gif(ctx, "fuck", "nsfw", target=miembro, action_templates=action_phrases)

    @commands.hybrid_command(name="cum_nsfw", description="Termina sobre otro usuario.")
    @commands.is_nsfw()
    async def cum_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} se corrió sobre {target}!",
            "{target} quedó cubierto por {author}.",
            "¡Un final feliz! {author} terminó sobre {target}.",
            "{author} llega al clímax, cubriendo a {target} con su esencia.",
            "Un final explosivo para {target}, cortesía de {author}.",
            "{target} recibe una cálida recompensa de {author}.",
            "La pasión de {author} culmina sobre el cuerpo de {target}.",
        ]
        # La categoría en la API es 'cum'
        await get_interactive_gif(ctx, "cum", "nsfw", target=miembro, action_templates=action_phrases)

    @commands.hybrid_command(name="handjob_nsfw", description="Hazle una paja a otro usuario.")
    @commands.is_nsfw()
    async def handjob_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} le está dando placer a {target} con sus manos.",
            "Las manos de {author} trabajan hábilmente sobre {target}.",
            "{target} se estremece ante el hábil toque de {author}.",
            "{author} sabe exactamente cómo usar sus manos para llevar a {target} al límite.",
            "Un trabajo manual experto de {author} para el deleite de {target}.",
            "El ritmo de {author} enloquece a {target}.",
        ]
        # La categoría en la API es 'handjob'
        await get_interactive_gif(ctx, "handjob", "nsfw", target=miembro, action_templates=action_phrases)

    @commands.hybrid_command(name="anal_nsfw", description="Ten sexo anal con otro usuario.")
    @commands.is_nsfw()
    async def anal_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} toma a {target} por detrás.",
            "¡Por la puerta de atrás! {author} y {target} tienen una sesión anal.",
            "{author} explora las profundidades de {target} con una intensidad ardiente.",
            "Un encuentro apasionado por la puerta trasera entre {author} y {target}.",
            "{target} se arquea de placer mientras {author} lo toma.",
            "La conexión entre {author} y {target} es profunda y prohibida.",
        ]
        # La categoría en la API es 'anal'
        await get_interactive_gif(ctx, "anal", "nsfw", target=miembro, action_templates=action_phrases)

    @commands.hybrid_command(name="boobjob_nsfw", description="Hazle una paja con los pechos a alguien.")
    @commands.is_nsfw()
    async def boobjob_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} usa sus pechos para darle placer a {target}.",
            "{target} se pierde entre los pechos de {author}.",
            "{author} envuelve a {target} con sus pechos, creando una fricción celestial.",
            "El paraíso se encuentra entre los pechos de {author}, y {target} lo sabe bien.",
            "Una suave y placentera sesión de 'paizuri' de {author} para {target}.",
            "{target} se pierde en un mar de suavidad gracias a {author}.",
        ]
        # La categoría en la API es 'paizuri' (término japonés para boobjob)
        await get_interactive_gif(ctx, "paizuri", "nsfw", target=miembro, action_templates=action_phrases)

async def setup(bot: commands.Bot):
    await bot.add_cog(NSFWCog(bot))