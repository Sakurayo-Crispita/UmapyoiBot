import asyncio
import aiohttp
import os
import sqlite3
import importlib
import sys
from dotenv import load_dotenv

# Añadir el directorio raíz al path para poder importar módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import api_helpers
from utils import database_manager

async def test_gemini(session):
    print("\n[1] Probando Gemini API (gemini-2.0-flash)...")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY no encontrada en .env")
        return False
    
    response = await api_helpers.ask_gemini(session, api_key, "Responde con la palabra 'OK' si me escuchas.")
    print(f"Respuesta de Gemini: {response}")
    if "Error" in response or "❌" in response or "⚠️" in response:
        print("❌ Prueba de Gemini fallida.")
        return False
    print("✅ Prueba de Gemini exitosa.")
    return True

async def test_jikan(session):
    print("\n[2] Probando Jikan API (Búsqueda de Anime)...")
    response = await api_helpers.search_anime(session, "Naruto")
    if response and "error" not in response and response.get('title'):
        print(f"✅ Búsqueda exitosa. Anime encontrado: {response['title']}")
        return True
    else:
        print(f"❌ Prueba de Jikan fallida. Respuesta: {response}")
        return False

async def test_waifupics(session):
    print("\n[3] Probando waifu.pics API (Interacción)...")
    try:
        async with session.get("https://api.waifu.pics/sfw/hug", timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('url'):
                    print(f"✅ waifu.pics exitoso. URL obtenida: {data['url']}")
                    return True
            print(f"❌ waifu.pics fallido. Status: {response.status}")
            return False
    except Exception as e:
        print(f"❌ waifu.pics fallido. Error: {e}")
        return False

async def test_nekosbest(session):
    print("\n[4] Probando nekos.best API (Respaldo/Baka)...")
    try:
        async with session.get("https://nekos.best/api/v2/baka", timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("results") and data["results"][0].get("url"):
                    print(f"✅ nekos.best exitoso. URL obtenida: {data['results'][0]['url']}")
                    return True
            print(f"❌ nekos.best fallido. Status: {response.status}")
            return False
    except Exception as e:
        print(f"❌ nekos.best fallido. Error: {e}")
        return False

def test_database():
    print("\n[5] Probando Inicialización de Base de Datos...")
    try:
        database_manager.setup_database()
        
        with sqlite3.connect("bot_data.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
        
        required_tables = ['server_settings', 'balances', 'economy_settings', 'levels', 'warnings']
        missing = [t for t in required_tables if t not in tables]
        
        if missing:
            print(f"❌ Faltan tablas en la DB: {missing}")
            return False
        print("✅ Base de datos inicializada correctamente.")
        return True
    except Exception as e:
        print(f"❌ Error probando base de datos: {e}")
        return False

def test_cogs():
    print("\n[6] Probando imports de Cogs...")
    cogs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cogs")
    all_good = True
    
    for filename in os.listdir(cogs_dir):
        if filename.endswith(".py"):
            cog_name = filename[:-3]
            try:
                # Import the module to ensure there are no syntax errors
                importlib.import_module(f"cogs.{cog_name}")
                print(f"✅ Cog '{cog_name}' importado correctamente.")
            except Exception as e:
                print(f"❌ Error al importar Cog '{cog_name}': {e}")
                all_good = False
                
    return all_good


async def run_all_tests():
    print("Iniciando pruebas de APIs y componentes críticos de UmapyoiBot...")
    load_dotenv()
    
    # Crear una sesión compartida para todas las pruebas asíncronas
    async with aiohttp.ClientSession() as session:
        result_gemini = await test_gemini(session)
        result_jikan = await test_jikan(session)
        result_waifu = await test_waifupics(session)
        result_nekos = await test_nekosbest(session)
        
    result_db = test_database()
    result_cogs = test_cogs()
    
    print("\n" + "="*40)
    print("RESUMEN DE PRUEBAS:")
    print(f"Gemini API:   {'✅' if result_gemini else '❌'}")
    print(f"Jikan API:    {'✅' if result_jikan else '❌'}")
    print(f"Waifu.pics:   {'✅' if result_waifu else '❌'}")
    print(f"Nekos.best:   {'✅' if result_nekos else '❌'}")
    print(f"Database:     {'✅' if result_db else '❌'}")
    print(f"Cogs Imports: {'✅' if result_cogs else '❌'}")
    print("="*40)

if __name__ == "__main__":
    asyncio.run(run_all_tests())
