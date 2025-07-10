import discord
from discord.ext import commands
import aiohttp
import random
from typing import Literal, Optional, List, Tuple
import asyncio

# --- CONFIGURACIÓN DE APIS ---
# Definimos las APIs y sus características para que el helper sepa cómo usarlas.
# Formato: (url_base, ruta_de_la_url, campo_del_resultado)
API_CONFIG = {
    "nekos.best": ("https://nekos.best/api/v2/", "{category}", "url"),
    "nekos.life": ("https://nekos.life/api/v2/img/", "{category}", "url"),
    "waifu.pics": ("https://api.waifu.pics/", "{gif_type}/{category}", "url")
}

# --- MAPA DE CATEGORÍAS A APIS ---
# Para cada categoría, definimos una lista de APIs a intentar en orden de prioridad.
# También mapeamos el nombre de nuestra categoría al nombre que usa la API.
CATEGORY_MAP = {
    # NSFW
    "anal": [("nekos.life", "anal")],
    "paizuri": [("nekos.best", "paizuri")],
    "fuck": [("nekos.best", "fuck"), ("nekos.life", "classic")],
    "cum": [("nekos.best", "cum")],
    "handjob": [("nekos.best", "handjob")],
    "boobs": [("nekos.best", "boobs"), ("nekos.life", "boobs")],
    "pussy": [("nekos.best", "pussy"), ("nekos.life", "pussy")],
    "neko_nsfw": [("nekos.best", "neko"), ("nekos.life", "nsfw_neko_gif")],
    "waifu_nsfw": [("nekos.best", "waifu")],
    "blowjob": [("nekos.best", "blowjob"), ("nekos.life", "blowjob")],
    # SFW
    "kiss": [("waifu.pics", "kiss")],
    "cuddle": [("waifu.pics", "cuddle")],
    "hug": [("waifu.pics", "hug")],
    "pat": [("waifu.pics", "pat")],
    "slap": [("waifu.pics", "slap")],
    "tickle": [("nekos.life", "tickle")],
    "poke": [("waifu.pics", "poke")],
    "baka": [("nekos.life", "baka")],
    "highfive": [("waifu.pics", "highfive")],
    "bonk": [("waifu.pics", "bonk")],
    "blush": [("waifu.pics", "blush")],
}


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
    Una función centralizada y robusta que intenta obtener GIFs de múltiples APIs.
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

    # Lógica Multi-API
    # Si la categoría no está en nuestro mapa, no podemos hacer nada.
    internal_category = f"{category}_nsfw" if gif_type == "nsfw" and category in ["neko", "waifu"] else category
    
    if internal_category not in CATEGORY_MAP:
        await ctx.send(f"La categoría '{internal_category}' no está configurada internamente.", ephemeral=True)
        return

    # Intentamos obtener el GIF de las APIs definidas en el mapa
    gif_url = None
    used_api_name = ""
    apis_to_try = CATEGORY_MAP[internal_category]

    timeout = aiohttp.ClientTimeout(total=8) # 8 segundos de timeout
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for api_name, api_category in apis_to_try:
            base_url, path_template, result_field = API_CONFIG[api_name]
            api_url = f"{base_url}{path_template.format(category=api_category, gif_type=gif_type)}"
            
            try:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Extraer la URL según la estructura de la API
                        if api_name == "nekos.best":
                            url = data.get('results', [{}])[0].get(result_field)
                        else: # nekos.life, waifu.pics
                            url = data.get(result_field)
                        
                        if url:
                            gif_url = url
                            used_api_name = api_name
                            break # ¡Éxito! Salimos del bucle.
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                print(f"API '{api_name}' falló para la categoría '{category}': {e}")
                continue # Intentamos con la siguiente API

    # Enviar el resultado
    if gif_url:
        embed = discord.Embed(description=action_text, color=ctx.author.color)
        embed.set_image(url=gif_url)
        embed.set_footer(text=f"Solicitado por {ctx.author.display_name} | API: {used_api_name}")
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"No se pudo obtener un GIF para '{category}' después de intentar con todas las APIs disponibles.", ephemeral=True)


# --- GEMINI (IA) HELPER CON TIMEOUT ---
async def ask_gemini(api_key: str, question: str) -> str:
    # (Este código no cambia)
    if not api_key:
        return "❌ La función de IA no está configurada por el dueño del bot."
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": question}]}]}
    headers = {"Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=20)
    try:
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


# --- JIKAN (ANIME) HELPER CON TIMEOUT ---
async def search_anime(query: str) -> Optional[dict]:
    # (Este código no cambia)
    api_url = f"https://api.jikan.moe/v4/anime?q={query.replace(' ', '%20')}&limit=1"
    timeout = aiohttp.ClientTimeout(total=10)
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
        return {"error": str(e)}