import pytest
import os
import sqlite3
import discord
from discord.ext import commands
import asyncio
import aiohttp

# Forzamos que la base de datos use memoria RAM en las pruebas
os.environ["BOT_TEST_DB"] = ":memory:"

# Importamos el database_manager (después del environ override)
from utils import database_manager as db

class MockAvatar:
    @property
    def url(self):
        return "http://mock.avatar/url.png"

class MockUser(discord.Object):
    def __init__(self, id: int, name: str):
        super().__init__(id)
        self.name = name
        self.bot = False
        self.display_name = name
        self.display_avatar = MockAvatar()
        self.guild = discord.Object(id=12345)

class MockGuild(discord.Object):
    def __init__(self, id: int, name: str):
        super().__init__(id)
        self.name = name

class MockMessage:
    def __init__(self, content):
        self.content = content

class MockContext:
    def __init__(self, bot, guild: MockGuild, author: MockUser):
        self.bot = bot
        self.guild = guild
        self.author = author
        self.channel = discord.Object(id=111)
        self.message = MockMessage("!mock")
        # Record of responses configured to assert in tests
        self.responses = []
        self.ephemeral_responses = []

    async def send(self, content=None, embed=None, ephemeral=False, **kwargs):
        msg = content or (embed.description if embed else "")
        if ephemeral:
            self.ephemeral_responses.append(msg)
        else:
            self.responses.append(msg)
        return MockMessage(msg)
        
    async def reply(self, *args, **kwargs):
        return await self.send(*args, **kwargs)

    async def defer(self, ephemeral=False):
        pass

@pytest.fixture(scope="session")
def event_loop():
    """Generates an isolated event loop for the test session."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
async def setup_test_db():
    """Configura la base de datos temporal antes de CADA prueba y la limpia después."""
    # Obtenemos la conexión (al ser :memory:, se crea vacía)
    conn = db.get_connection()
    db.setup_database() # Ejecuta la creación de tablas
    
    yield
    
    # Limpieza: Borrar todas las tablas
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    for table in tables:
        # SQLite system tables cannot be dropped
        if table[0] != "sqlite_sequence":
            cursor.execute(f"DELETE FROM {table[0]};")
    conn.commit()

class MyMockBot(commands.Bot):
    @property
    def user(self):
        return MockUser(1234, "UmapyoiMock")

@pytest.fixture
def mock_bot():
    bot = MyMockBot(command_prefix="!", intents=discord.Intents.default())
    bot.CREAM_COLOR = discord.Color(0xFFFDD0)
    return bot

@pytest.fixture
async def session():
    """Provee una sesión HTTP asíncrona genérica para los tests de APIs externos."""
    async with aiohttp.ClientSession() as s:
        yield s

@pytest.fixture
def mock_ctx(mock_bot):
    guild = MockGuild(12345, "Test Server")
    author = MockUser(999, "TestUser")
    return MockContext(mock_bot, guild, author)
