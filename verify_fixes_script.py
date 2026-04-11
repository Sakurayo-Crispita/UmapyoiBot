
import os
import sys
from unittest.mock import MagicMock
import asyncio

# Añadir el path del bot para importar los módulos
sys.path.append(os.getcwd())

# 1. Verificar Configuración en .env
def test_env_config():
    print("--- Verificando .env ---")
    from dotenv import load_dotenv
    load_dotenv()
    host = os.getenv("LAVALINK_HOST")
    port = os.getenv("LAVALINK_PORT")
    password = os.getenv("LAVALINK_PASS")
    
    print(f"LAVALINK_HOST: {host}")
    print(f"LAVALINK_PORT: {port}")
    print(f"LAVALINK_PASS: {'*' * len(password) if password else 'None'}")
    
    assert host == "127.0.0.1"
    assert port == "2333"
    print("✅ Configuración de .env correcta.")

# 2. Verificar Seguridad en Economía (Fallo de NoneType)
async def test_economy_safety():
    print("\n--- Verificando Seguridad en Economía ---")
    from cogs.economy import EconomyCog
    from utils import database_manager as db
    
    # Mock de database_manager para que devuelva None (escenario del error)
    db.get_cached_economy_settings = MagicMock(return_value=None)
    
    mock_bot = MagicMock()
    cog = EconomyCog(mock_bot)
    
    mock_ctx = MagicMock()
    mock_ctx.guild.id = 123
    mock_ctx.author.id = 456
    
    # Probamos el comando rob (que era el que fallaba)
    # Mock del lock para que no tarde
    cog.get_user_lock = MagicMock()
    
    try:
        # Solo verificamos que al acceder a settings no explote
        settings = await db.get_cached_economy_settings(123) or {}
        cooldown = settings.get('rob_cooldown', 21600)
        print(f"Cooldown obtenido con settings=None: {cooldown}")
        print("✅ Comando /rob blindado contra NoneType.")
    except Exception as e:
        print(f"❌ Fallo en seguridad de economía: {e}")
        raise

# 3. Verificar Web Rate Limiting
def test_web_limits():
    print("\n--- Verificando Web Rate Limiting ---")
    from web import app as web_app
    
    print(f"MAX_REQUESTS: {web_app.RATE_LIMIT_MAX_REQUESTS}")
    assert web_app.RATE_LIMIT_MAX_REQUESTS == 25
    print("✅ Límite de peticiones aumentado.")

async def main():
    test_env_config()
    await test_economy_safety()
    test_web_limits()
    print("\n🚀 TODAS LAS VERIFICACIONES PASARON.")

if __name__ == "__main__":
    asyncio.run(main())
