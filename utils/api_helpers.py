import discord
from discord.ext import commands
import aiohttp
import random
from typing import Literal, Optional
import asyncio

# --- FUNCIÓN ORIGINAL (SIN CAMBIOS) ---
async def get_interactive_gif(
    session: aiohttp.ClientSession, 
    ctx: commands.Context,
    category: str,
    gif_type: Literal["sfw", "nsfw"],
    target: Optional[discord.Member] = None,
    action_templates: list[str] = [],
    self_action_phrases: list[str] = []
):
    """
    Función que ahora usa la sesión de aiohttp compartida del bot.
    """
    await ctx.defer(ephemeral=False)

    if target and target != ctx.author:
        templates = action_templates
    else:
        if not self_action_phrases:
            await ctx.send("No puedes realizar esta acción contigo mismo.", ephemeral=True)
            return
        templates = self_action_phrases
    
    action_text = random.choice(templates).format(author=ctx.author.mention, target=target.mention if target else "")

    api_url = f"https://api.waifu.pics/{gif_type}/{category}"
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with session.get(api_url, timeout=timeout) as response:
            if response.status == 404:
                await ctx.send(f"❌ La categoría '{category}' no fue encontrada en la API. Se usará un reemplazo.", ephemeral=True)
                api_url = f"https://api.waifu.pics/{gif_type}/waifu"
                async with session.get(api_url, timeout=timeout) as fallback_response:
                    if fallback_response.status != 200:
                        await ctx.send("Error incluso con la API de respaldo. Por favor, reporta esto.", ephemeral=True)
                        return
                    response = fallback_response
            
            if response.status == 200:
                data = await response.json()
                gif_url = data.get('url')
                if gif_url:
                    embed = discord.Embed(description=action_text, color=ctx.author.color)
                    embed.set_image(url=gif_url)
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("La API no devolvió una URL válida.", ephemeral=True)
            else:
                await ctx.send(f"La API devolvió un error inesperado (Estado: {response.status}).", ephemeral=True)

    except asyncio.TimeoutError:
        await ctx.send("La API tardó demasiado en responder. Inténtalo de nuevo más tarde.", ephemeral=True)
    except Exception as e:
        print(f"Error crítico en get_interactive_gif: {e}")
        await ctx.send("Ocurrió un error inesperado al procesar tu solicitud.", ephemeral=True)


# --- NUEVA FUNCIÓN PARA LA API NEKOS.BEST ---
async def get_nekos_best_gif(
    session: aiohttp.ClientSession,
    ctx: commands.Context,
    category: str,
    target: Optional[discord.Member] = None,
    action_templates: list[str] = []
):
    """
    Obtiene un GIF de la API nekos.best.
    """
    await ctx.defer(ephemeral=False)
    
    action_text = random.choice(action_templates).format(author=ctx.author.mention, target=target.mention if target else "")
    api_url = f"https://nekos.best/api/v2/{category}"
    timeout = aiohttp.ClientTimeout(total=10)

    try:
        async with session.get(api_url, timeout=timeout) as response:
            if response.status == 200:
                data = await response.json()
                # La estructura de esta API es diferente
                gif_url = data.get("results", [{}])[0].get("url")
                if gif_url:
                    embed = discord.Embed(description=action_text, color=ctx.author.color)
                    embed.set_image(url=gif_url)
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("La API (nekos.best) no devolvió una URL válida.", ephemeral=True)
            else:
                await ctx.send(f"La API (nekos.best) devolvió un error (Estado: {response.status}).", ephemeral=True)
    except asyncio.TimeoutError:
        await ctx.send("La API (nekos.best) tardó demasiado en responder.", ephemeral=True)
    except Exception as e:
        print(f"Error crítico en get_nekos_best_gif: {e}")
        await ctx.send("Ocurrió un error inesperado al procesar tu solicitud.", ephemeral=True)


# --- GEMINI Y JIKAN HELPERS (SIN CAMBIOS) ---
async def ask_gemini(api_key: str, question: str) -> str:
    if not api_key:
        return "❌ La función de IA no está configurada por el dueño del bot."
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": question}]}]}
    headers = {"Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        # Usamos una sesión local aquí ya que no es parte del bot principal
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(api_url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'candidates' in data and data['candidates']:
                        return data['candidates'][0]['content']['parts'][0]['text']
                    else:
                        return "La IA no pudo generar una respuesta esta vez."
                else:
                    return f"Error al contactar la API de Gemini: {response.status}"
    except asyncio.TimeoutError:
        return "La IA tardó demasiado en responder."
    except Exception as e:
        return f"Ocurrió un error inesperado: {e}"

async def search_anime(query: str) -> Optional[dict]:
    api_url = f"https://api.jikan.moe/v4/anime?q={query.replace(' ', '%20')}&limit=1"
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        # Usamos una sesión local aquí también
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
        return {"error": str(e)}