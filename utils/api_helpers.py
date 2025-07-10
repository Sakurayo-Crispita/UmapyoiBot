import discord
from discord.ext import commands
import aiohttp
import random
from typing import Literal, Optional, List, Tuple
import asyncio

# --- CONFIGURACIÓN DE APIS (MÁS EXTENSA) ---
# Se define cómo interactuar con cada API.
API_CONFIG = {
    "waifu.pics": {
        "base_url": "https://api.waifu.pics/",
        "path_template": "{gif_type}/{category}",
        "result_path": ["url"]
    },
    "nekos.best": {
        "base_url": "https://nekos.best/api/v2/",
        "path_template": "{category}",
        "result_path": ["results", 0, "url"]
    },
    "nekobot.xyz": {
        "base_url": "https://nekobot.xyz/api/image",
        "params": {"type": "{category}"},
        "result_path": ["message"]
    },
    # Danbooru es muy bueno para tags específicos pero puede ser lento.
    "danbooru": {
        "base_url": "https://danbooru.donmai.us/posts.json",
        "params": {"limit": 100, "random": "true", "tags": "{category} rating:explicit"},
        "result_path": [0, "file_url"] # Tomamos el primer resultado de una búsqueda aleatoria
    }
}

# --- MAPA DE CATEGORÍAS A APIS (ESTRATEGIA DE FALLBACK) ---
# Para cada comando, definimos una lista de APIs a intentar en orden.
# Formato: [("nombre_api_en_config", "nombre_categoria_en_esa_api")]
CATEGORY_MAP = {
    # NSFW
    "anal": [("danbooru", "anal"), ("nekobot.xyz", "hanal")],
    "paizuri": [("danbooru", "paizuri"), ("nekos.best", "paizuri")],
    "fuck": [("nekos.best", "fuck"), ("danbooru", "sex")],
    "cum": [("danbooru", "cum"), ("nekos.best", "cum")],
    "handjob": [("danbooru", "handjob"), ("nekos.best", "handjob")],
    "boobs": [("danbooru", "breasts"), ("nekos.best", "boobs")],
    "pussy": [("nekobot.xyz", "pussy"), ("nekos.best", "pussy")],
    "neko_nsfw": [("nekos.best", "neko"), ("nekobot.xyz", "hneko")],
    "waifu_nsfw": [("nekos.best", "waifu")],
    "blowjob": [("danbooru", "blowjob"), ("nekos.best", "blowjob")],
    
    # SFW (usando waifu.pics como principal)
    "kiss": [("waifu.pics", "kiss")],
    "cuddle": [("waifu.pics", "cuddle")],
    "hug": [("waifu.pics", "hug")],
    "pat": [("waifu.pics", "pat")],
    "slap": [("waifu.pics", "slap")],
    "poke": [("waifu.pics", "poke")],
    "baka": [("waifu.pics", "baka")], # waifu.pics ya tiene baka
    "highfive": [("waifu.pics", "highfive")],
    "bonk": [("waifu.pics", "bonk")],
    "blush": [("waifu.pics", "blush")],
    "tickle": [("waifu.pics", "tickle")],
}

async def _fetch_from_api(session, api_name, category, gif_type):
    """Función interna para manejar una sola llamada a API."""
    config = API_CONFIG.get(api_name)
    if not config:
        return None

    url = config["base_url"]
    params = {}
    
    if "path_template" in config:
        url += config["path_template"].format(category=category, gif_type=gif_type)
    
    if "params" in config:
        params = {k: v.format(category=category) for k, v in config["params"].items()}

    try:
        async with session.get(url, params=params) as response:
            if response.status != 200:
                print(f"API '{api_name}' devolvió estado {response.status} para '{category}'")
                return None
            
            data = await response.json()
            
            # Navegar la estructura del JSON para encontrar la URL
            value = data
            for key in config["result_path"]:
                if isinstance(value, list):
                    if isinstance(key, int) and len(value) > key:
                        value = value[key]
                    else: # Si la lista está vacía o el índice es inválido
                        # Para Danbooru, si la búsqueda no da resultados, la lista estará vacía
                        if api_name == "danbooru" and not value:
                             return None # No es un error, solo no hay resultados.
                        # Intentar con el primer elemento si no se especifica índice
                        value = random.choice(value) if value else None
                elif isinstance(value, dict):
                    value = value.get(key)
                else:
                    return None
            
            # Danbooru puede devolver URLs relativas
            if api_name == "danbooru" and value and not value.startswith("http"):
                value = f"https://danbooru.donmai.us{value}"

            # Asegurarse de que sea una URL de imagen/gif válida
            if isinstance(value, str) and value.startswith("http"):
                return value
            
    except (asyncio.TimeoutError, aiohttp.ClientError) as e:
        print(f"Error de conexión con API '{api_name}' para '{category}': {e}")
    except Exception as e:
        print(f"Error procesando respuesta de '{api_name}' para '{category}': {e}")
    
    return None

# --- GIF HELPER DEFINITIVO ---
async def get_interactive_gif(
    ctx: commands.Context,
    category: str,
    gif_type: Literal["sfw", "nsfw"],
    target: Optional[discord.Member] = None,
    action_templates: list[str] = [],
    self_action_phrases: list[str] = []
):
    """
    Intenta obtener un GIF de una lista priorizada de APIs hasta tener éxito.
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
    internal_category = f"{category}_nsfw" if gif_type == "nsfw" and category in ["neko", "waifu"] else category
    
    if internal_category not in CATEGORY_MAP:
        await ctx.send(f"La categoría '{internal_category}' no está configurada internamente.", ephemeral=True)
        return

    gif_url = None
    used_api_name = ""
    apis_to_try = CATEGORY_MAP[internal_category]

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for api_name, api_category in apis_to_try:
            print(f"Intentando API '{api_name}' con categoría '{api_category}'...")
            url = await _fetch_from_api(session, api_name, api_category, gif_type)
            if url:
                gif_url = url
                used_api_name = api_name
                break

    # Enviar el resultado
    if gif_url:
        embed = discord.Embed(description=action_text, color=ctx.author.color)
        embed.set_image(url=gif_url)
        embed.set_footer(text=f"Solicitado por {ctx.author.display_name} | API: {used_api_name}")
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"No se pudo obtener un GIF para '{category}' después de intentar con todas las APIs disponibles.", ephemeral=True)


# --- GEMINI Y JIKAN HELPERS (SIN CAMBIOS) ---
async def ask_gemini(api_key: str, question: str) -> str:
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

async def search_anime(query: str) -> Optional[dict]:
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