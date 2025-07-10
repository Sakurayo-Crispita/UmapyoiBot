import discord
from discord.ext import commands
import aiohttp
import random
from typing import Literal, Optional

# --- GIF HELPER ---
async def get_interactive_gif(
    ctx: commands.Context,
    category: str,
    gif_type: Literal["sfw", "nsfw"],
    target: Optional[discord.Member] = None,
    action_templates: list[str] = [],
    self_action_phrases: list[str] = []
):
    """
    Una función centralizada para obtener GIFs interactivos de una API.
    """
    await ctx.defer(ephemeral=False)

    if target and target != ctx.author:
        templates = action_templates
    else:
        if not self_action_phrases:
            await ctx.send("No puedes realizar esta acción contigo mismo.", ephemeral=True)
            return
        templates = self_action_phrases

    if gif_type == "sfw":
        api_url = f"https://api.waifu.pics/sfw/{category}"
    elif gif_type == "nsfw" and category in ["waifu", "neko", "blowjob"]:
        api_url = f"https://api.waifu.pics/nsfw/{category}"
    else:
        api_url = f"https://api.mywaifulist.moe/v1/nsfw/{category}"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    gif_url = data.get("url") or data.get("image")

                    if gif_url:
                        # Para los comandos estáticos, el texto es el título
                        if not target:
                             action_text = random.choice(templates)
                        else:
                            action_text = random.choice(templates).format(
                                author=ctx.author.mention,
                                target=target.mention if target else ""
                            )
                        
                        embed = discord.Embed(description=action_text, color=ctx.author.color)
                        embed.set_image(url=gif_url)
                        embed.set_footer(text=f"Solicitado por {ctx.author.display_name}")
                        await ctx.send(embed=embed)
                    else:
                        await ctx.send("No se pudo obtener un GIF de la API.", ephemeral=True)
                else:
                    await ctx.send(f"Error al contactar la API (Estado: {response.status}).", ephemeral=True)
        except Exception as e:
            print(f"Error en la función de GIF ({category}): {e}")
            await ctx.send("Ocurrió un error inesperado al obtener el GIF.", ephemeral=True)


# --- GEMINI (IA) HELPER ---
async def ask_gemini(api_key: str, question: str) -> str:
    """
    Envía una pregunta a la API de Google Gemini y devuelve la respuesta.
    """
    if not api_key:
        return "❌ La función de IA no está configurada por el dueño del bot."

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": question}]}]}
    headers = {"Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'candidates' in data and data['candidates']:
                        return data['candidates'][0]['content']['parts'][0]['text']
                    else:
                        # Esto puede pasar si la respuesta fue bloqueada por filtros de seguridad.
                        return "La IA no pudo generar una respuesta esta vez. Intenta reformular tu pregunta."
                else:
                    error_details = await response.text()
                    print(f"Error de la API de Gemini: {response.status} - {error_details}")
                    return f"Error al contactar la API de Gemini. Código: {response.status}"
    except Exception as e:
        print(f"Error en ask_gemini: {e}")
        return f"Ocurrió un error inesperado al procesar tu pregunta: {e}"


# --- JIKAN (ANIME) HELPER ---
async def search_anime(query: str) -> Optional[dict]:
    """
    Busca un anime en la API de Jikan (MyAnimeList).
    """
    api_url = f"https://api.jikan.moe/v4/anime?q={query.replace(' ', '%20')}&limit=1"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['data'][0] if data.get('data') else None
                else:
                    # Devuelve el código de error para que el comando pueda manejarlo
                    return {"error": response.status}
    except Exception as e:
        print(f"Error en search_anime: {e}")
        return {"error": str(e)}

