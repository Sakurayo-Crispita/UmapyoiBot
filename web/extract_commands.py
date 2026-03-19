import os
import json
import asyncio
import importlib
import sys
import discord
from discord.ext import commands

# Añadimos el directorio raíz al path para poder importar cogs y utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

async def extract_commands():
    print("Extrayendo comandos de los Cogs...")
    
    # Mock bot for inspection
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", help_command=None, intents=intents)
    
    # Añadimos atributos que los cogs esperan encontrar en el bot
    bot.GENIUS_API_TOKEN = None
    bot.CREAM_COLOR = 0xFFF5E1
    bot.PINK_COLOR = 0xFF69B4
    bot.YDL_OPTIONS = {}
    bot.FFMPEG_OPTIONS = {}

    # Mapeo de iconos de Lucide
    icon_mapping = {
        "Economy": "coins",
        "Fun": "sparkles",
        "Gambling": "dice-5",
        "Interaccion": "heart",
        "Leveling": "trending-up",
        "Moderation": "shield",
        "Music": "music",
        "Serverconfig": "settings",
        "Tts": "mic",
        "Utility": "wrench"
    }
    
    cogs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'cogs'))
    commands_data = []

    for filename in sorted(os.listdir(cogs_dir)):
        if filename.endswith('.py') and not filename.startswith('__'):
            cog_name = filename[:-3]
            try:
                # Importamos el cog dinámicamente
                module = importlib.import_module(f'cogs.{cog_name}')
                # Buscamos la clase del cog
                for name, obj in module.__dict__.items():
                    if isinstance(obj, type) and issubclass(obj, commands.Cog):
                        # Instanciamos el cog (con bot=None ya que solo queremos inspeccionar)
                        try:
                            cog_instance = obj(bot)
                            cog_commands = []
                            
                            for command in cog_instance.get_commands():
                                if command.hidden: continue
                                cog_commands.append({
                                    "name": command.name,
                                    "usage": f"/{command.name} {command.signature}" if command.signature else f"/{command.name}",
                                    "desc": command.description or command.help or "Sin descripción."
                                })
                            
                            if cog_commands:
                                category_name = cog_name.capitalize()
                                commands_data.append({
                                    "category": category_name,
                                    "icon": icon_mapping.get(category_name, "box"),
                                    "commands": sorted(cog_commands, key=lambda x: x['name'])
                                })
                        except Exception as e:
                            print(f"Error al instanciar {cog_name}: {e}")
            except Exception as e:
                print(f"Error al cargar {cog_name}: {e}")

    # Ordenar por categoría
    commands_data.sort(key=lambda x: x['category'])

    output_path = os.path.join(os.path.dirname(__file__), 'static', 'commands.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(commands_data, f, indent=4, ensure_ascii=False)
    
    print(f"Comandos extraídos exitosamente en {output_path}")

if __name__ == "__main__":
    asyncio.run(extract_commands())
