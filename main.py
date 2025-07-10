# main.py
import discord
from discord.ext import commands
import os
import asyncio
import sqlite3
from typing import Optional
from dotenv import load_dotenv
from utils import database_manager

# --- CONFIGURACIÓN DE APIS Y CONSTANTES ---
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DB_FILE = "bot_data.db" 

# --- CLASE DE BOT PERSONALIZADA ---
class UmapyoiBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # OJO: La constante DB_FILE aquí debe coincidir con el nombre de tu archivo de DB
        self.db_file = DB_FILE 

        # --- CONSTANTES GLOBALES DEL BOT ---
        self.GENIUS_API_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN")
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        self.CREAM_COLOR = discord.Color.from_str("#F0EAD6")
        self.FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -ar 48000 -ac 2 -b:a 192k'
        }
        self.YDL_OPTIONS = {
            'format': 'bestaudio[ext=webm][acodec=opus]/bestaudio/best',
            'quiet': True, 'default_search': 'ytsearch', 'source_address': '0.0.0.0',
            'noplaylist': True, 'cookiefile': 'cookies.txt',
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        }

    async def setup_hook(self):
        print("Verificando y creando tablas de la base de datos si no existen...")
        # Llama a la función de configuración desde el gestor
        database_manager.setup_database()
        print('-----------------------------------------')
        
        print("Cargando Cogs...")
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"✅ Cog '{filename[:-3]}' cargado.")
                except Exception as e:
                    print(f"❌ Error al cargar el Cog '{filename[:-3]}': {e}")
        print("Cogs cargados.")
        print("-----------------------------------------")
        print("Sincronizando comandos slash...")
        await self.tree.sync()
        print("¡Comandos sincronizados!")

    async def close(self):
        await super().close()

# --- DEFINICIÓN DE INTENTS E INICIO DEL BOT ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.members = True

bot = UmapyoiBot(command_prefix='!', intents=intents, case_insensitive=True, help_command=None)

# --- EVENTOS GLOBALES DEL BOT ---
@bot.event
async def on_ready():
    print(f'¡Umapyoi está en línea! Conectado como {bot.user}')
    await bot.change_presence(activity=discord.Game(name="Música y Juegos | /help"))

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    if bot.user.mentioned_in(message) and not message.mention_everyone and not message.reference:
        await message.channel.send(f'¡Hola, {message.author.mention}! Usa `/help` para ver todos mis comandos. ✨')
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Espera {round(error.retry_after, 1)} segundos.", ephemeral=True)
    elif isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ No tienes los permisos necesarios para usar este comando.", ephemeral=True)
    elif isinstance(error, commands.BotMissingPermissions):
        permisos = ", ".join(p.replace('_', ' ').capitalize() for p in error.missing_permissions)
        await ctx.send(f"⚠️ No puedo ejecutar esa acción porque me faltan los siguientes permisos: **{permisos}**", ephemeral=True)
    elif isinstance(error, commands.errors.HybridCommandError) and isinstance(error.original, discord.errors.InteractionResponded):
        print("Ignorando error 'Interaction has already been responded to.'")
    elif isinstance(error, commands.errors.HybridCommandError) and isinstance(error.original, discord.errors.NotFound):
        print(f"Ignorando error 'Not Found' (Código: {error.original.code}). Probablemente la interacción expiró.")
    else:
        import traceback
        print(f"Error no manejado en '{ctx.command.name if ctx.command else 'Comando desconocido'}':")
        traceback.print_exception(type(error), error, error.__traceback__)

def main():
    if not DISCORD_TOKEN:
        print("¡ERROR! No se encontró el DISCORD_TOKEN.")
        return
    try:
        bot.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure:
        print("\n¡ERROR! El token de Discord no es válido.")
    except Exception as e:
        print(f"\nOcurrió un error crítico al iniciar el bot: {e}")

if __name__ == "__main__":
    main()