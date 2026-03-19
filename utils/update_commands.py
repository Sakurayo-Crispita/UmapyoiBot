"""
Automated command sync: generates web/static/commands.json from bot cogs.
Run: python utils/update_commands.py
"""
import os, sys, asyncio, json
os.environ.setdefault("DISCORD_TOKEN", "mock")
os.environ.setdefault("OWNER_ID", "123456789")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

import discord
from discord.ext import commands

class MockBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix='!', intents=intents, help_command=None)
        self.CREAM_COLOR = discord.Color(0xFFFDD0)
        self.GENIUS_API_TOKEN = "mock"
        self.GEMINI_API_KEY = "mock"
        self.http_session = None
        self.start_time = None

CATEGORY_ICONS = {
    "Configuración del Servidor": "settings",
    "Economía": "coins",
    "Interacción": "heart",
    "Juegos de Azar": "dice-5",
    "Juegos e IA": "bot",
    "Moderación": "shield",
    "Música": "music",
    "Niveles": "trending-up",
    "Roles por Reacción": "at-sign",
    "Texto a Voz": "mic",
    "Tickets": "ticket",
    "Utilidad": "wrench",
}

async def update_json():
    bot = MockBot()
    data = {}  # keyed by category name to merge duplicates
    seen_cogs = set()

    for filename in sorted(os.listdir('./cogs')):
        if filename.endswith('.py') and filename != '__init__.py':
            cog_name = filename[:-3]
            try:
                await bot.load_extension(f'cogs.{cog_name}')
                
                # Process any NEW cogs that appeared after loading this extension
                for cog_key in list(bot.cogs.keys()):
                    if cog_key in seen_cogs:
                        continue
                    seen_cogs.add(cog_key)
                    cog = bot.get_cog(cog_key)
                    
                    # Merge into existing category or create new
                    if cog_key not in data:
                        data[cog_key] = {"category": cog_key, "icon": CATEGORY_ICONS.get(cog_key, "box"), "commands": []}
                    
                    cmd_names_seen = {c["name"] for c in data[cog_key]["commands"]}
                    
                    for cmd in sorted(cog.walk_commands(), key=lambda c: c.qualified_name):
                        if cmd.hidden or cmd.qualified_name in cmd_names_seen:
                            continue
                        cmd_names_seen.add(cmd.qualified_name)
                        usage = f"/{cmd.qualified_name}"
                        for name, param in cmd.clean_params.items():
                            if param.default is param.empty:
                                usage += f" <{name}>"
                            else:
                                usage += f" [{name}]"
                        data[cog_key]["commands"].append({
                            "name": cmd.qualified_name,
                            "usage": usage,
                            "desc": cmd.description or "Sin descripcion disponible."
                        })
            except Exception as e:
                print(f"[WARN] Skipped {cog_name}: {e}")

    # Filter out empty categories and convert to list
    result = [v for v in data.values() if v["commands"]]

    out = os.path.join(PROJECT_ROOT, 'web', 'static', 'commands.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

    total = sum(len(c['commands']) for c in result)
    print(f"Done! {len(result)} categories, {total} commands -> {out}")

if __name__ == "__main__":
    asyncio.run(update_json())
