"""Tests de conectividad con APIs externas y verificación de imports.
Estos tests hacen llamadas reales a APIs — pueden fallar por red/rate limits.
Marca: pytest -m api para ejecutar solo estos.
"""
import pytest
import asyncio
import aiohttp
import os
import importlib
import sys
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import api_helpers
from utils import database_manager


@pytest.fixture
async def http_session():
    """Provee una sesión HTTP asíncrona para los tests de APIs."""
    async with aiohttp.ClientSession() as s:
        yield s


# --- Tests de APIs Externas (marcados como 'api') ---

@pytest.mark.api
async def test_gemini(http_session):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY no configurada en .env")

    response = await api_helpers.ask_gemini(http_session, api_key, "Responde solo 'OK'.")
    assert "Error" not in response and "❌" not in response, f"Gemini falló: {response}"


@pytest.mark.api
async def test_jikan(http_session):
    response = await api_helpers.search_anime(http_session, "Naruto")
    assert response is not None, "Jikan no devolvió resultados"
    assert "error" not in response, f"Jikan devolvió error: {response}"
    assert response.get('title'), "Jikan no devolvió título"


@pytest.mark.api
async def test_waifupics(http_session):
    async with http_session.get("https://api.waifu.pics/sfw/hug", timeout=aiohttp.ClientTimeout(total=10)) as resp:
        assert resp.status == 200, f"waifu.pics devolvió status {resp.status}"
        data = await resp.json()
        assert data.get('url'), "waifu.pics no devolvió URL"


@pytest.mark.api
async def test_nekosbest(http_session):
    async with http_session.get("https://nekos.best/api/v2/baka", timeout=aiohttp.ClientTimeout(total=10)) as resp:
        assert resp.status == 200, f"nekos.best devolvió status {resp.status}"
        data = await resp.json()
        assert data.get("results") and data["results"][0].get("url"), "nekos.best no devolvió URL"


# --- Tests de Infraestructura (siempre corren) ---

def test_database():
    """Verifica que la base de datos se inicializa correctamente."""
    import sqlite3
    database_manager.setup_database()
    conn = database_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]

    required = ['server_settings', 'balances', 'economy_settings', 'levels', 'warnings']
    missing = [t for t in required if t not in tables]
    assert not missing, f"Faltan tablas: {missing}"


def test_cogs():
    """Verifica que todos los cogs se importan sin errores."""
    cogs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cogs")
    failures = []
    for filename in os.listdir(cogs_dir):
        if filename.endswith(".py") and not filename.startswith("_"):
            try:
                importlib.import_module(f"cogs.{filename[:-3]}")
            except Exception as e:
                failures.append(f"{filename}: {e}")
    assert not failures, f"Cogs con errores:\n" + "\n".join(failures)
