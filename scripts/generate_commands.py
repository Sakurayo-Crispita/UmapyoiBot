import asyncio
import os
import sys
import json
import discord
from discord.ext import commands
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment
os.environ["DISCORD_TOKEN"] = "dummy"
os.environ["OWNER_ID"] = "123"

class DummyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.GENIUS_API_TOKEN = "dummy_token"
        self.GEMINI_API_KEY = "dummy_key"
        from utils import constants
        self.CREAM_COLOR = discord.Color(constants.CREAM_COLOR)
        self.FFMPEG_OPTIONS = constants.FFMPEG_OPTIONS
        self.YDL_OPTIONS = constants.YDL_OPTIONS

async def main():
    bot = DummyBot()
    
    # Load all cogs
    cogs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cogs')
    for filename in os.listdir(cogs_dir):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
            except Exception as e:
                print(f"Error loading {filename}: {e}")

    categories = {}
    
    icon_map = {
        "Economía": "coins",
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

    for cog_name, cog in bot.cogs.items():
        cat_name = cog_name
        if cat_name not in categories:
            categories[cat_name] = []
            
        for cmd in cog.get_commands():
            if cmd.hidden:
                continue
            
            # Formatear usage
            params = []
            for name, param in cmd.clean_params.items():
                if param.required:
                    params.append(f"<{name}>")
                else:
                    params.append(f"[{name}]")
            
            usage_str = f"/{cmd.name} {' '.join(params)}".strip()
            
            categories[cat_name].append({
                "name": cmd.name,
                "usage": usage_str,
                "desc": cmd.description or cmd.short_doc or "Sin descripción"
            })

    # Prepare final JSON structure
    final_output = []
    for cat, cmds in sorted(categories.items()):
        if not cmds: continue
        
        icon = icon_map.get(cat, "box")
        
        final_output.append({
            "category": cat,
            "icon": icon,
            "commands": sorted(cmds, key=lambda c: c['name'])
        })
        
    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web', 'static', 'commands.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=4, ensure_ascii=False)
        
    print(f"Successfully generated {out_path} with {sum(len(c['commands']) for c in final_output)} commands.")

if __name__ == "__main__":
    asyncio.run(main())
