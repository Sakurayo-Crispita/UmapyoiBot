import discord
from discord.ext import commands
import aiohttp, random, asyncio
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from typing import Literal, Optional

class FunCog(commands.Cog, name="Juegos e IA"):
    """Comandos interactivos y divertidos para pasar el rato."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Función para obtener GIFs interactivos ---
    async def get_interactive_gif(self, ctx: commands.Context, target: discord.Member, category: str, action_templates: list[str], color: discord.Color):
        await ctx.defer(ephemeral=False)
        
        if ctx.author == target:
            await ctx.send("No puedes realizar esta acción contigo mismo.", ephemeral=True)
            return

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"https://api.waifu.pics/sfw/{category}") as response:
                    if response.status == 200:
                        data = await response.json()
                        gif_url = data.get("url")
                        if gif_url:
                            action_text = random.choice(action_templates).format(
                                author=ctx.author.mention,
                                target=target.mention
                            )
                            
                            embed = discord.Embed(description=action_text, color=color)
                            embed.set_image(url=gif_url)
                            await ctx.send(embed=embed)
                        else:
                            await ctx.send("No se pudo obtener un GIF.", ephemeral=True)
                    else:
                        await ctx.send(f"Error al contactar la API (Estado: {response.status}).", ephemeral=True)
            except Exception as e:
                print(f"Error en el comando interactivo {category}: {e}")
                await ctx.send("Ocurrió un error inesperado.", ephemeral=True)

    # --- Comandos existentes ---

    @commands.hybrid_command(name='pregunta', description="Hazme cualquier pregunta y usaré mi IA para responder.")
    async def pregunta(self, ctx: commands.Context, *, pregunta: str):
        await ctx.defer()
        
        if not self.bot.GEMINI_API_KEY:
            return await ctx.send("❌ La función de IA no está configurada por el dueño del bot.")
            
        API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={self.bot.GEMINI_API_KEY}"
        
        payload = {"contents": [{"parts": [{"text": pregunta}]}]}
        headers = {"Content-Type": "application/json"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(API_URL, json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'candidates' in data and data['candidates']:
                            respuesta_ia = data['candidates'][0]['content']['parts'][0]['text']
                        else:
                            respuesta_ia = "La IA no pudo generar una respuesta esta vez."
                    else:
                        error_details = await response.text()
                        print(f"Error de la API de Gemini: {response.status} - {error_details}")
                        respuesta_ia = f"Error al contactar la API de Gemini. Código: {response.status}"
        except Exception as e:
            respuesta_ia = f"Ocurrió un error inesperado: {e}"

        embed = discord.Embed(title="🤔 Pregunta para Umapyoi", description=f"**Tú preguntaste:**\n{pregunta}", color=discord.Color.gold())
        embed.add_field(name="💡 Mi Respuesta:", value=respuesta_ia)
        await ctx.send(embed=embed)

    def process_wanted_image(self, template_bytes: bytes, avatar_bytes: bytes) -> BytesIO:
        template = Image.open(BytesIO(template_bytes)).convert("RGBA")
        avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
        avatar_size = (833, 820); paste_position = (96, 445)
        avatar = avatar.resize(avatar_size)
        template.paste(avatar, paste_position, avatar)
        final_buffer = BytesIO()
        template.save(final_buffer, format="PNG")
        final_buffer.seek(0)
        return final_buffer

    @commands.hybrid_command(name='wanted', description="Crea un cartel de 'Se Busca' para un usuario.")
    async def wanted(self, ctx: commands.Context, miembro: Optional[discord.Member] = None):
        await ctx.defer()
        miembro = miembro or ctx.author
        try:
            wanted_template_url = "https://i.imgur.com/wNvXv8i.jpeg"
            headers = {'User-Agent': 'Mozilla/5.0'}
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(wanted_template_url) as resp:
                    if resp.status != 200: return await ctx.send(f"❌ No pude descargar la plantilla. Estado: {resp.status}")
                    template_bytes = await resp.read()
                async with session.get(miembro.display_avatar.url) as resp:
                    if resp.status != 200: return await ctx.send("❌ No pude descargar el avatar.")
                    avatar_bytes = await resp.read()
            loop = asyncio.get_event_loop()
            buffer = await loop.run_in_executor(None, self.process_wanted_image, template_bytes, avatar_bytes)
            file = discord.File(buffer, filename="wanted.png")
            await ctx.send(file=file)
        except Exception as e:
            print(f"Error en /wanted: {e}")
            await ctx.send(f"❌ No pude crear el cartel. Error: {e}")

    @commands.hybrid_command(name='ppt', description="Juega Piedra, Papel o Tijera contra mí.")
    async def ppt(self, ctx: commands.Context, eleccion: Literal['piedra', 'papel', 'tijera']):
        opciones = ['piedra', 'papel', 'tijera']
        eleccion_usuario = eleccion.lower()
        eleccion_bot = random.choice(opciones)
        if eleccion_usuario == eleccion_bot:
            resultado = f"¡Empate! Ambos elegimos **{eleccion_bot}**."
        elif (eleccion_usuario == 'piedra' and eleccion_bot == 'tijera') or \
             (eleccion_usuario == 'papel' and eleccion_bot == 'piedra') or \
             (eleccion_usuario == 'tijera' and eleccion_bot == 'papel'):
            resultado = f"¡Ganaste! Yo elegí **{eleccion_bot}**."
        else:
            resultado = f"¡Perdiste! Yo elegí **{eleccion_bot}**."
        await ctx.send(f"Tú elegiste **{eleccion_usuario}**. {resultado}")
                    
    @commands.hybrid_command(name='anime', description="Busca información detallada sobre un anime.")
    async def anime(self, ctx: commands.Context, *, nombre: str):
        await ctx.defer()
        API_URL = f"https://api.jikan.moe/v4/anime?q={nombre.replace(' ', '%20')}&limit=1"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL) as response:
                    if response.status == 200:
                        data = await response.json()
                        if not data['data']:
                            return await ctx.send(f"❌ No encontré ningún anime llamado `{nombre}`.", ephemeral=True)

                        anime_data = data['data'][0]
                        synopsis = anime_data.get('synopsis', 'No hay sinopsis disponible.')
                        if len(synopsis) > 1000:
                            synopsis = synopsis[:1000] + "..."

                        embed = discord.Embed(
                            title=anime_data.get('title', 'N/A'),
                            url=anime_data.get('url', ''),
                            description=synopsis,
                            color=discord.Color.blue()
                        )

                        if image_url := anime_data.get('images', {}).get('jpg', {}).get('large_image_url'):
                            embed.set_thumbnail(url=image_url)

                        embed.add_field(name="Puntuación", value=f"⭐ {anime_data.get('score', 'N/A')}", inline=True)
                        embed.add_field(name="Episodios", value=anime_data.get('episodes', 'N/A'), inline=True)
                        embed.add_field(name="Estado", value=anime_data.get('status', 'N/A'), inline=True)

                        genres = [genre['name'] for genre in anime_data.get('genres', [])]
                        if genres:
                            embed.add_field(name="Géneros", value=", ".join(genres), inline=False)

                        embed.set_footer(text=f"Fuente: MyAnimeList | ID: {anime_data.get('mal_id')}")

                        await ctx.send(embed=embed)
                    else:
                        await ctx.send(f"❌ Hubo un error con la API (Código: {response.status}). Inténtalo de nuevo más tarde.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Ocurrió un error inesperado: {e}", ephemeral=True)

    # --- Comandos Interactivos (SFW) ---
    
    @commands.hybrid_command(name="kiss", description="Besa a otro usuario.")
    async def kiss(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} le dio un tierno beso a {target}.",
            "¡Un beso robado! {author} acaba de besar a {target}.",
            "Los labios de {author} y {target} se encontraron en un dulce beso.",
            "{author} se acercó y le plantó un beso suave a {target}.",
            "Un momento mágico: {author} besó a {target} con ternura.",
            "{target} se sonrojó después de recibir un beso de {author}.",
            "¡Qué romántico! {author} y {target} compartieron un beso.",
            "{author} no pudo resistirse y besó a {target}.",
            "El aire se llenó de chispas cuando {author} besó a {target}."
        ]
        await self.get_interactive_gif(ctx, miembro, "kiss", action_phrases, discord.Color.magenta())

    @commands.hybrid_command(name="cuddle", description="Acurrúcate con otro usuario.")
    async def cuddle(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} se acurrucó tiernamente con {target}.",
            "{author} y {target} están en un abrazo muy cercano.",
            "¡Qué momento tan tierno! {author} está abrazando a {target}.",
            "Nada como un buen acurrucamiento entre {author} y {target}.",
            "{author} encontró consuelo en los brazos de {target}."
        ]
        await self.get_interactive_gif(ctx, miembro, "cuddle", action_phrases, discord.Color.green())

    @commands.hybrid_command(name="hug", description="Dale un abrazo a otro usuario.")
    async def hug(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} le dio un gran abrazo a {target}.",
            "{target} recibió un cálido abrazo de {author}.",
            "{author} rodeó a {target} con sus brazos en un abrazo.",
            "¡Abrazo grupal! Bueno, solo entre {author} y {target} por ahora.",
            "Un abrazo de oso de {author} para {target}."
        ]
        await self.get_interactive_gif(ctx, miembro, "hug", action_phrases, discord.Color.teal())

    @commands.hybrid_command(name="pat", description="Dale una palmadita en la cabeza a alguien.")
    async def pat(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} le dio unas palmaditas en la cabeza a {target}. ¡Qué tierno!",
            "{target} recibió unas suaves palmaditas de {author}.",
            "¡Buen chico/a! {author} acaricia la cabeza de {target}.",
            "Una palmadita de aprobación de {author} para {target}.",
            "{author} le muestra su afecto a {target} con una palmadita."
        ]
        await self.get_interactive_gif(ctx, miembro, "pat", action_phrases, discord.Color.gold())

    @commands.hybrid_command(name="slap", description="Dale una bofetada a alguien.")
    async def slap(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "¡ZAS! {author} le dio una bofetada a {target}.",
            "{target} sintió la mano de {author} en su mejilla.",
            "Parece que {target} se lo merecía... {author} le dio una cachetada.",
            "¡Auch! Esa bofetada de {author} a {target} debió doler.",
            "{author} le dejó la cara roja a {target} con una bofetada."
        ]
        await self.get_interactive_gif(ctx, miembro, "slap", action_phrases, discord.Color.orange())


async def setup(bot: commands.Bot):
    await bot.add_cog(FunCog(bot))