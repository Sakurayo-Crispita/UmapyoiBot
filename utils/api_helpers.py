import discord
from discord.ext import commands
import aiohttp
import random
from typing import Literal, Optional
import asyncio

# --- GIF HELPER MEJORADO ---
async def get_interactive_gif(
    ctx: commands.Context,
    category: str,
    gif_type: Literal["sfw", "nsfw"],
    target: Optional[discord.Member] = None,
    action_templates: list[str] = [],
    self_action_phrases: list[str] = []
):
    """
    Una función centralizada para obtener GIFs interactivos de APIs estables.
    Prioriza Nekos.best para NSFW y Waifu.pics para SFW.
    """
    await ctx.defer(ephemeral=False)

    # Determinar el texto de la acción
    if target and target != ctx.author:
        templates = action_templates
    else:
        if not self_action_phrases:
            await ctx.send("No puedes realizar esta acción contigo mismo.", ephemeral=True)
            return
        templates = self_action_phrases
    
    action_text = random.choice(templates)
    if target:
        action_text = action_text.format(author=ctx.author.mention, target=target.mention)
    else:
        action_text = action_text.format(author=ctx.author.mention)

    # Determinar la URL de la API
    # Nekos.best es la API principal para NSFW, Waifu.pics para SFW
    if gif_type == "nsfw":
        api_url = f"https://nekos.best/api/v2/{category}"
    else: # sfw
        api_url = f"https://api.waifu.pics/sfw/{category}"

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Nekos.best anida los resultados en una lista "results"
                    if 'results' in data:
                        gif_url = data['results'][0]['url']
                    # Waifu.pics tiene la URL directamente
                    else:
                        gif_url = data.get('url')

                    if gif_url:
                        embed = discord.Embed(description=action_text, color=ctx.author.color)
                        embed.set_image(url=gif_url)
                        embed.set_footer(text=f"Solicitado por {ctx.author.display_name} | API: {'nekos.best' if gif_type == 'nsfw' else 'waifu.pics'}")
                        await ctx.send(embed=embed)
                    else:
                        await ctx.send("La API no devolvió un GIF válido. Inténtalo de nuevo.", ephemeral=True)
                
                elif response.status == 404:
                     await ctx.send(f"❌ La categoría '{category}' no fue encontrada en la API.", ephemeral=True)
                else:
                    await ctx.send(f"Error al contactar la API (Estado: {response.status}).", ephemeral=True)

        except asyncio.TimeoutError:
            await ctx.send("La API tardó demasiado en responder. Inténtalo más tarde.", ephemeral=True)
        except Exception as e:
            print(f"Error en la función de GIF ({category}): {e}")
            await ctx.send("Ocurrió un error inesperado al obtener el GIF.", ephemeral=True)


# --- GEMINI (IA) HELPER CON TIMEOUT ---
async def ask_gemini(api_key: str, question: str) -> str:
    """
    Envía una pregunta a la API de Google Gemini y devuelve la respuesta.
    """
    if not api_key:
        return "❌ La función de IA no está configurada por el dueño del bot."

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": question}]}]}
    headers = {"Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=20) # 20 segundos para la IA

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(api_url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'candidates' in data and data['candidates']:
                        return data['candidates'][0]['content']['parts'][0]['text']
                    else:
                        return "La IA no pudo generar una respuesta esta vez. Intenta reformular tu pregunta."
                else:
                    error_details = await response.text()
                    print(f"Error de la API de Gemini: {response.status} - {error_details}")
                    return f"Error al contactar la API de Gemini. Código: {response.status}"
    except asyncio.TimeoutError:
        return "La IA tardó demasiado en responder. Inténtalo más tarde."
    except Exception as e:
        print(f"Error en ask_gemini: {e}")
        return f"Ocurrió un error inesperado al procesar tu pregunta: {e}"


# --- JIKAN (ANIME) HELPER CON TIMEOUT ---
async def search_anime(query: str) -> Optional[dict]:
    """
    Busca un anime en la API de Jikan (MyAnimeList).
    """
    api_url = f"https://api.jikan.moe/v4/anime?q={query.replace(' ', '%20')}&limit=1"
    timeout = aiohttp.ClientTimeout(total=10) # 10 segundos
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['data'][0] if data.get('data') else None
                else:
                    return {"error": response.status}
    except asyncio.TimeoutError:
        return {"error": "Timeout"}
    except Exception as e:
        print(f"Error en search_anime: {e}")
        return {"error": str(e)}
