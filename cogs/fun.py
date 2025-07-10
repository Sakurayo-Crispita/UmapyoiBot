import discord
from discord.ext import commands
import random
from PIL import Image
from io import BytesIO
from typing import Literal, Optional
import aiohttp
from utils.constants import WANTED_TEMPLATE_URL
# Importamos nuestros helpers de API
from utils.api_helpers import ask_gemini, search_anime

# --- DICCIONARIOS DE TRADUCCIÓN ---
# Para traducir campos que vienen en inglés de la API
STATUS_TRANSLATIONS = {
    "Finished Airing": "Finalizado",
    "Currently Airing": "En Emisión",
    "Not yet aired": "Próximamente"
}

GENRE_TRANSLATIONS = {
    "Action": "Acción", "Adventure": "Aventura", "Comedy": "Comedia", "Drama": "Drama",
    "Sci-Fi": "Ciencia Ficción", "Fantasy": "Fantasía", "Horror": "Terror", "Romance": "Romance",
    "Mystery": "Misterio", "Slice of Life": "Recuentos de la vida", "Supernatural": "Sobrenatural",
    "Sports": "Deportes", "Suspense": "Suspense", "Award Winning": "Galardonado"
}


class FunCog(commands.Cog, name="Juegos e IA"):
    """Comandos de juegos, IA y otros entretenimientos."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name='pregunta', description="Hazme cualquier pregunta y usaré mi IA para responder.")
    async def pregunta(self, ctx: commands.Context, *, pregunta: str):
        await ctx.defer()
        
        # Llamamos a nuestra función de ayuda centralizada
        respuesta_ia = await ask_gemini(self.bot.GEMINI_API_KEY, pregunta)

        embed = discord.Embed(title="🤔 Pregunta para Umapyoi", description=f"**Tú preguntaste:**\n{pregunta}", color=discord.Color.gold())
        embed.add_field(name="💡 Mi Respuesta:", value=respuesta_ia)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='anime', description="Busca información detallada sobre un anime.")
    async def anime(self, ctx: commands.Context, *, nombre: str):
        await ctx.defer()
        
        anime_data = await search_anime(nombre)

        if not anime_data:
            return await ctx.send(f"❌ No encontré ningún anime llamado `{nombre}`.", ephemeral=True)
        
        if "error" in anime_data:
            return await ctx.send(f"❌ Hubo un error con la API (Código: {anime_data['error']}). Inténtalo de nuevo más tarde.", ephemeral=True)

        # --- LÓGICA DE TRADUCCIÓN ---

        # 1. Buscar el título en español
        title_es = next((t['title'] for t in anime_data.get('titles', []) if t['type'] == 'Spanish'), None)
        display_title = title_es or anime_data.get('title', 'N/A')

        # 2. Traducir la sinopsis usando la IA
        synopsis_en = anime_data.get('synopsis', 'No hay sinopsis disponible.')
        if synopsis_en and len(synopsis_en) > 20: # Solo traducir si hay algo sustancial
            prompt = f"Traduce el siguiente resumen de un anime al español de forma natural y atractiva:\n\n---\n{synopsis_en}\n---"
            synopsis_es = await ask_gemini(self.bot.GEMINI_API_KEY, prompt)
        else:
            synopsis_es = "No hay sinopsis disponible."

        if len(synopsis_es) > 1024:
            synopsis_es = synopsis_es[:1021] + "..."
        
        # 3. Traducir estado y géneros
        status_en = anime_data.get('status', 'N/A')
        status_es = STATUS_TRANSLATIONS.get(status_en, status_en)

        genres_en = [genre['name'] for genre in anime_data.get('genres', [])]
        genres_es = [GENRE_TRANSLATIONS.get(g, g) for g in genres_en]

        # --- CREACIÓN DEL EMBED EN ESPAÑOL ---
        embed = discord.Embed(
            title=display_title,
            url=anime_data.get('url', ''),
            description=synopsis_es,
            color=discord.Color.blue()
        )

        if image_url := anime_data.get('images', {}).get('jpg', {}).get('large_image_url'):
            embed.set_thumbnail(url=image_url)

        embed.add_field(name="Puntuación", value=f"⭐ {anime_data.get('score', 'N/A')}", inline=True)
        embed.add_field(name="Episodios", value=anime_data.get('episodes', 'N/A'), inline=True)
        embed.add_field(name="Estado", value=status_es, inline=True)

        if genres_es:
            embed.add_field(name="Géneros", value=", ".join(genres_es), inline=False)

        embed.set_footer(text=f"Fuente: MyAnimeList | ID: {anime_data.get('mal_id')}")

        await ctx.send(embed=embed)

    # --- Comandos que no usan APIs externas (se mantienen igual) ---

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
            wanted_template_url = WANTED_TEMPLATE_URL 
            headers = {'User-Agent': 'Mozilla/5.0'}
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(wanted_template_url) as resp:
                    if resp.status != 200: return await ctx.send(f"❌ No pude descargar la plantilla. Estado: {resp.status}")
                    template_bytes = await resp.read()
                async with session.get(miembro.display_avatar.url) as resp:
                    if resp.status != 200: return await ctx.send("❌ No pude descargar el avatar.")
                    avatar_bytes = await resp.read()
            
            buffer = await self.bot.loop.run_in_executor(None, self.process_wanted_image, template_bytes, avatar_bytes)
            
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

async def setup(bot: commands.Bot):
    await bot.add_cog(FunCog(bot))