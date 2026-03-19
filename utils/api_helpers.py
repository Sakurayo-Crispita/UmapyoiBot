import discord
from discord.ext import commands
import aiohttp
import random
from typing import Literal, Optional
import asyncio

# - FUNCIÓN ORIGINAL (SIN CAMBIOS) -
async def get_interactive_gif(
    session: aiohttp.ClientSession, 
    ctx: commands.Context,
    category: str,
    gif_type: Literal["sfw", "nsfw"],
    target: Optional[discord.Member] = None,
    action_templates: list[str] = [],
    self_action_phrases: list[str] = []
):
    try:
        await ctx.defer(ephemeral=False)
    except:
        pass

    if target and target != ctx.author:
        templates = action_templates
    else:
        if not self_action_phrases:
            await ctx.send("No puedes realizar esta acción contigo mismo.", ephemeral=True)
            return
        templates = self_action_phrases
    
    action_text = random.choice(templates).format(author=ctx.author.mention, target=target.mention if target else "")
    api_url = f"https://api.waifu.pics/{gif_type}/{category}"
    timeout = aiohttp.ClientTimeout(total=12)

    async def fetch_url(url):
        async with session.get(url, timeout=timeout) as resp:
            if resp.status == 200:
                return await resp.json(), 200
            return None, resp.status

    try:
        data, status = await fetch_url(api_url)

        if status == 404:
            await ctx.send(f"❌ La categoría '{category}' no fue encontrada en la API. Se usará un reemplazo.", ephemeral=True)
            api_url = f"https://api.waifu.pics/{gif_type}/waifu"
            data, status = await fetch_url(api_url)

        if status == 200 and data:
            gif_url = data.get('url')
            if gif_url:
                embed = discord.Embed(description=action_text, color=ctx.author.color)
                embed.set_image(url=gif_url)
                await ctx.send(embed=embed)
            else:
                await ctx.send("La API no devolvió una URL válida.", ephemeral=True)
        else:
            await ctx.send(f"La API devolvió un error (Estado: {status}).", ephemeral=True)

    except asyncio.TimeoutError:
        await ctx.send("La API tardó demasiado en responder. Inténtalo de nuevo más tarde.", ephemeral=True)
    except Exception as e:
        print(f"Error crítico en get_interactive_gif ({category}): {e}")
        await ctx.send("Ocurrió un error inesperado al procesar tu solicitud.", ephemeral=True)


# - NUEVA FUNCIÓN PARA LA API NEKOS.BEST -
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
    try:
        await ctx.defer(ephemeral=False)
    except:
        pass
    
    action_text = random.choice(action_templates).format(author=ctx.author.mention, target=target.mention if target else "")
    api_url = f"https://nekos.best/api/v2/{category}"
    timeout = aiohttp.ClientTimeout(total=10)

    try:
        async with session.get(api_url, timeout=timeout) as response:
            if response.status == 200:
                data = await response.json()
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


# - GEMINI Y JIKAN HELPERS (ACTUALIZADOS) -
async def ask_gemini(session: aiohttp.ClientSession, api_key: str, question: str) -> str:
    """Envía una pregunta a la API de Gemini y devuelve la respuesta.
    Usa la sesión HTTP compartida del bot y el modelo gemini-2.0-flash."""
    if not api_key:
        return "❌ La función de IA no está configurada por el dueño del bot."
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": question}]}]}
    headers = {"Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with session.post(api_url, json=payload, headers=headers, timeout=timeout) as response:
            if response.status == 200:
                data = await response.json()
                # Manejar respuestas bloqueadas por seguridad
                if not data.get('candidates'):
                    block_reason = data.get('promptFeedback', {}).get('blockReason', 'desconocida')
                    return f"⚠️ La IA no pudo responder. Razón de bloqueo: {block_reason}"
                
                candidate = data['candidates'][0]
                finish_reason = candidate.get('finishReason', '')
                
                if finish_reason == 'SAFETY':
                    return "⚠️ La IA bloqueó la respuesta por motivos de seguridad. Intenta reformular tu pregunta."
                
                parts = candidate.get('content', {}).get('parts', [])
                if parts and parts[0].get('text'):
                    return parts[0]['text']
                else:
                    return "La IA no pudo generar una respuesta esta vez."
            elif response.status == 400:
                return "❌ Error en la solicitud a Gemini. Verifica que la pregunta sea válida."
            elif response.status == 403:
                return "❌ La API key de Gemini no es válida o ha expirado."
            elif response.status == 429:
                return "⏳ Se ha excedido el límite de solicitudes a la IA. Inténtalo de nuevo en un momento."
            else:
                return f"Error al contactar la API de Gemini: {response.status}"
    except asyncio.TimeoutError:
        return "La IA tardó demasiado en responder."
    except Exception as e:
        return f"Ocurrió un error inesperado: {e}"

async def search_anime(session: aiohttp.ClientSession, query: str) -> Optional[dict]:
    """Busca información de un anime usando la API de Jikan (MyAnimeList).
    Usa la sesión HTTP compartida del bot."""
    api_url = f"https://api.jikan.moe/v4/anime?q={query.replace(' ', '%20')}&limit=1"
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with session.get(api_url, timeout=timeout) as response:
            if response.status == 200:
                data = await response.json()
                return data['data'][0] if data.get('data') else None
            else:
                return {"error": response.status}
    except asyncio.TimeoutError:
        return {"error": "Timeout"}
    except Exception as e:
        return {"error": str(e)}

# - DASHBOARD HELPERS -
async def create_discord_message(channel_id: int, payload: dict, bot_token: str) -> Optional[int]:
    """Crea un mensaje en un canal de Discord directamente vía HTTP API (usado por el dashboard)."""
    api_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(api_url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('id')
                else:
                    error = await resp.text()
                    print(f"Error creando mensaje por API: {resp.status} - {error}")
                    return None
        except Exception as e:
            print(f"Excepción creando mensaje: {e}")
            return None

async def add_discord_reaction(channel_id: int, message_id: int, emoji: str, bot_token: str) -> bool:
    """Añade una reacción a un mensaje en Discord directamente vía HTTP API."""
    import urllib.parse
    encoded_emoji = urllib.parse.quote(emoji)
    api_url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
    headers = {"Authorization": f"Bot {bot_token}"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.put(api_url, headers=headers) as resp:
                if resp.status != 204:
                    error = await resp.text()
                    print(f"Error añadiendo reacción por API: {resp.status} - {error}")
                return resp.status == 204
        except Exception as e:
            print(f"Excepción añadiendo reacción: {e}")
            return False