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

        # --- LÓGICA DE TRADUCCIÓN (SIN IA) ---

        # 1. Buscar el título en español
        title_es = next((t['title'] for t in anime_data.get('titles', []) if t['type'] == 'Spanish'), None)
        display_title = title_es or anime_data.get('title', 'N/A')

        # 2. Usar la sinopsis original en inglés para mayor fiabilidad
        synopsis = anime_data.get('synopsis', 'No hay sinopsis disponible.')
        if len(synopsis) > 1024:
            synopsis = synopsis[:1021] + "..."
        
        # 3. Traducir estado y géneros
        status_en = anime_data.get('status', 'N/A')
        status_es = STATUS_TRANSLATIONS.get(status_en, status_en)

        genres_en = [genre['name'] for genre in anime_data.get('genres', [])]
        genres_es = [GENRE_TRANSLATIONS.get(g, g) for g in genres_en]

        # --- CREACIÓN DEL EMBED ---
        embed = discord.Embed(
            title=display_title,
            url=anime_data.get('url', ''),
            description=synopsis,
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

    # --- NUEVOS COMANDOS DE DIVERSIÓN ---

    @commands.hybrid_command(name="8ball", description="Pregúntale a la bola 8 mágica sobre tu futuro.")
    async def eight_ball(self, ctx: commands.Context, *, pregunta: str):
        respuestas = [
            "En mi opinión, sí.", "Es cierto.", "Es decididamente así.", "Probablemente.",
            "Buen pronóstico.", "Todo apunta a que sí.", "Sin duda.", "Sí.", "Puedes contar con ello.",
            "Respuesta vaga, vuelve a intentarlo.", "Pregunta en otro momento.", "Será mejor que no te lo diga ahora.",
            "No puedo predecirlo ahora.", "Concéntrate y vuelve a preguntar.", "No cuentes con ello.",
            "Mi respuesta es no.", "Mis fuentes me dicen que no.", "Las perspectivas no son buenas.", "Muy dudoso."
        ]
        respuesta = random.choice(respuestas)
        embed = discord.Embed(title="🎱 La Bola 8 Mágica", color=discord.Color.dark_blue())
        embed.add_field(name="Tu Pregunta", value=pregunta, inline=False)
        embed.add_field(name="Mi Respuesta", value=respuesta, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="coinflip", description="Lanza una moneda al aire.")
    async def coinflip(self, ctx: commands.Context):
        resultado = random.choice(["Cara", "Cruz"])
        emoji = "🪙"
        await ctx.send(f"{emoji} ¡Ha salido **{resultado}**!")

    @commands.hybrid_command(name="rolldice", description="Lanza uno o más dados.")
    async def rolldice(self, ctx: commands.Context, cantidad: int = 1, caras: int = 6):
        if cantidad > 100:
            return await ctx.send("No puedo lanzar más de 100 dados a la vez.", ephemeral=True)
        if caras > 1000:
            return await ctx.send("El dado no puede tener más de 1000 caras.", ephemeral=True)
        
        rolls = [random.randint(1, caras) for _ in range(cantidad)]
        total = sum(rolls)
        
        embed = discord.Embed(title="🎲 Lanzamiento de Dados", color=discord.Color.red())
        embed.add_field(name="Resultados", value=f"`{', '.join(map(str, rolls))}`", inline=False)
        if cantidad > 1:
            embed.add_field(name="Total", value=f"**{total}**", inline=False)
            
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ship", description="Mide la compatibilidad entre dos personas.")
    async def ship(self, ctx: commands.Context, persona1: discord.Member, persona2: Optional[discord.Member] = None):
        target2 = persona2 or ctx.author
        
        # Para que el resultado sea siempre el mismo para la misma pareja
        seed = hash(f"{min(persona1.id, target2.id)}-{max(persona1.id, target2.id)}")
        random.seed(seed)
        
        percentage = random.randint(0, 100)
        
        if percentage < 20:
            comment = "Hmm... quizás solo como amigos."
        elif percentage < 40:
            comment = "Hay una pequeña chispa, ¿quizás?"
        elif percentage < 60:
            comment = "¡Una compatibilidad decente!"
        elif percentage < 80:
            comment = "¡Wow, aquí hay potencial!"
        else:
            comment = "¡Están hechos el uno para el otro! ❤️"
            
        # Barra de progreso
        filled_blocks = int(percentage / 10)
        empty_blocks = 10 - filled_blocks
        progress_bar = '🟥' * filled_blocks + '⬜' * empty_blocks

        embed = discord.Embed(
            title=f"💖 Test de Compatibilidad 💖",
            description=f"Analizando la conexión entre **{persona1.display_name}** y **{target2.display_name}**...",
            color=discord.Color.light_grey()
        )
        embed.add_field(name="Resultado", value=f"## `{percentage}%`\n`{progress_bar}`\n\n**{comment}**")
        
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(FunCog(bot))
