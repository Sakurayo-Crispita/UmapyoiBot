import discord
from discord.ext import commands
import aiohttp
import random

class NSFWCog(commands.Cog, name="NSFW"):
    """
    Comandos NSFW que solo se pueden usar en canales marcados como tal.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Función para obtener imágenes estáticas (waifu.pics) ---
    async def get_waifu_pics_image(self, ctx: commands.Context, category: str, title: str, color: discord.Color):
        await ctx.defer(ephemeral=False) 
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"https://api.waifu.pics/nsfw/{category}") as response:
                    if response.status == 200:
                        data = await response.json()
                        image_url = data.get("url")
                        if image_url:
                            embed = discord.Embed(title=title, color=color)
                            embed.set_image(url=image_url)
                            embed.set_footer(text=f"Solicitado por {ctx.author.display_name}")
                            await ctx.send(embed=embed)
                        else:
                            await ctx.send("La API no devolvió una imagen válida.", ephemeral=True)
                    else:
                        await ctx.send(f"Error al contactar la API (Estado: {response.status}).", ephemeral=True)
            except Exception as e:
                print(f"Error en el comando {category}: {e}")
                await ctx.send("Ocurrió un error inesperado.", ephemeral=True)

    # --- Función para obtener GIFs interactivos (nekos.best) ---
    async def get_nekos_best_gif(self, ctx: commands.Context, target: discord.Member, category: str, action_templates: list[str]):
        await ctx.defer(ephemeral=False)
        
        if ctx.author == target:
            await ctx.send("No puedes realizar esta acción contigo mismo.", ephemeral=True)
            return
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"https://nekos.best/api/v2/{category}") as response:
                    if response.status == 200:
                        data = await response.json()
                        gif_url = data["results"][0]["url"]
                        anime_name = data["results"][0]["anime_name"]
                        
                        if gif_url:
                            action_text = random.choice(action_templates).format(
                                author=ctx.author.mention,
                                target=target.mention
                            )
                            embed = discord.Embed(description=action_text, color=discord.Color.random())
                            embed.set_image(url=gif_url)
                            if anime_name != "Desconocido":
                                embed.set_footer(text=f"Anime: {anime_name}")
                            await ctx.send(embed=embed)
                        else:
                            await ctx.send("No se pudo obtener un GIF.", ephemeral=True)
                    else:
                        # Si nekos.best falla, intentamos con otra API como respaldo
                        async with session.get(f"https://api.waifu.pics/nsfw/{category}") as backup_response:
                            if backup_response.status == 200:
                                data = await backup_response.json()
                                gif_url = data.get("url")
                                if gif_url:
                                    action_text = random.choice(action_templates).format(author=ctx.author.mention, target=target.mention)
                                    embed = discord.Embed(description=action_text, color=discord.Color.random())
                                    embed.set_image(url=gif_url)
                                    await ctx.send(embed=embed)
                                else:
                                    await ctx.send("Ambas APIs fallaron. Inténtalo de nuevo más tarde.", ephemeral=True)
                            else:
                                await ctx.send(f"Error al contactar ambas APIs (Estados: {response.status}, {backup_response.status}).", ephemeral=True)
            except Exception as e:
                print(f"Error en el comando interactivo {category}: {e}")
                await ctx.send("Ocurrió un error inesperado.", ephemeral=True)

    # --- Comandos Estáticos ---

    @commands.hybrid_command(name="neko_nsfw", description="Muestra una imagen NSFW de una neko.")
    @commands.is_nsfw()
    async def neko_nsfw(self, ctx: commands.Context):
        await self.get_waifu_pics_image(ctx, "neko", "Neko NSFW", discord.Color.purple())

    @commands.hybrid_command(name="waifu_nsfw", description="Muestra una imagen NSFW de una waifu.")
    @commands.is_nsfw()
    async def waifu_nsfw(self, ctx: commands.Context):
        await self.get_waifu_pics_image(ctx, "waifu", "Waifu NSFW", discord.Color.pink())

    @commands.hybrid_command(name="trap_nsfw", description="Muestra una imagen NSFW de una trap.")
    @commands.is_nsfw()
    async def trap_nsfw(self, ctx: commands.Context):
        await self.get_waifu_pics_image(ctx, "trap", "Trap NSFW", discord.Color.blue())

    @commands.hybrid_command(name="blowjob_nsfw", description="Muestra una imagen NSFW de un blowjob.")
    @commands.is_nsfw()
    async def blowjob_nsfw(self, ctx: commands.Context):
        await self.get_waifu_pics_image(ctx, "blowjob", "Blowjob NSFW", discord.Color.red())

    @commands.hybrid_command(name="boobs_nsfw", description="Muestra una imagen NSFW de pechos.")
    @commands.is_nsfw()
    async def boobs_nsfw(self, ctx: commands.Context):
        # Esta categoría no está en waifu.pics, usamos nekos.best para una imagen estática
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
        # Esta categoría no está en waifu.pics, usamos nekos.best para una imagen estática
        async with aiohttp.ClientSession() as session:
            async with session.get("https://nekos.best/api/v2/pussy") as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data["results"][0]["url"]
                    embed = discord.Embed(title="Pussy NSFW", color=discord.Color.dark_magenta())
                    embed.set_image(url=image_url)
                    await ctx.send(embed=embed)


    # --- Comandos Interactivos NSFW ---

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
        await self.get_nekos_best_gif(ctx, miembro, "fuck", action_phrases)

    @commands.hybrid_command(name="lick_nsfw", description="Lame a otro usuario.")
    @commands.is_nsfw()
    async def lick_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} le está dando una lamida a {target}.",
            "{target} siente la lengua de {author}...",
            "¡Una lamida juguetona de {author} para {target}!",
            "{author} saborea a {target} con una lamida.",
            "La lengua de {author} explora a {target}."
        ]
        await self.get_nekos_best_gif(ctx, miembro, "lick", action_phrases)

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
        await self.get_nekos_best_gif(ctx, miembro, "cum", action_phrases)

    @commands.hybrid_command(name="handjob_nsfw", description="Hazle una paja a otro usuario.")
    @commands.is_nsfw()
    async def handjob_nsfw(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} le está dando placer a {target} con sus manos.",
            "Las manos de {author} trabajan hábilmente sobre {target}.",
            "{target} disfruta de una buena paja de parte de {author}."
        ]
        await self.get_nekos_best_gif(ctx, miembro, "handjob", action_phrases)

async def setup(bot: commands.Bot):
    await bot.add_cog(NSFWCog(bot))
