import asyncio
import os
from dotenv import load_dotenv

# Importar el bot y la app web
from main import bot, DISCORD_TOKEN
from web.app import run_app

async def main():
    load_dotenv()
    
    # Cargar librería de voz en Linux si es necesario
    try:
        import discord
        if not discord.opus.is_loaded():
            discord.opus.load_opus('libopus.so.0')
    except Exception as e:
        print(f"Aviso: No se pudo cargar Opus manualmente: {e}")

    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_TOKEN no encontrado en el archivo .env")
        return

    print("--- Iniciando UmapyoiBot System ---")
    
    # Ejecutar ambos concurrentemente
    try:
        await asyncio.gather(
            bot.start(DISCORD_TOKEN),
            run_app()
        )
    except Exception as e:
        print(f"Error crítico en la ejecución: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSaliendo...")
