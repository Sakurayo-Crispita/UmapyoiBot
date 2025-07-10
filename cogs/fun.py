import discord
from discord.ext import commands
import aiohttp, random, asyncio
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from typing import Literal, Optional

class FunCog(commands.Cog, name="Juegos e IA"):
    """Comandos de juegos, IA y otros entretenimientos."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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

async def setup(bot: commands.Bot):
    await bot.add_cog(FunCog(bot))
