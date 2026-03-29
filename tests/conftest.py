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

# ============================================================
#  MOCKS — Simulan objetos de discord.py sin conectar a Discord
# ============================================================

class MockAvatar:
    @property
    def url(self):
        return "http://mock.avatar/url.png"

class MockVoiceChannel(discord.Object):
    def __init__(self, id: int = 777):
        super().__init__(id)
        self.name = "General Voice"

class MockVoiceState:
    def __init__(self, channel=None):
        self.channel = channel or MockVoiceChannel()

class MockUser(discord.Object):
    def __init__(self, id: int, name: str, bot: bool = False):
        super().__init__(id)
        self.name = name
        self.bot = bot
        self.display_name = name
        self.display_avatar = MockAvatar()
        self.guild = discord.Object(id=12345)
        self.mention = f"<@{id}>"
        self.color = discord.Color.blue()
        self.voice = None  # Se sobreescribe donde se necesite

    async def send(self, *args, **kwargs):
        pass

class MockRole(discord.Object):
    def __init__(self, id: int, name: str = "MockRole", position: int = 10):
        super().__init__(id)
        self.name = name
        self.position = position
        self.mention = f"<@&{id}>"

class MockGuild(discord.Object):
    def __init__(self, id: int, name: str):
        super().__init__(id)
        self.name = name
        self.owner_id = 11111111
        self.me = MockUser(1234, "UmapyoiMock", bot=True)
        self.voice_client = None
        self.icon = None
        self._roles = {}

    def get_role(self, role_id):
        return self._roles.get(role_id)

    def get_channel(self, channel_id):
        return None

class MockMessage:
    def __init__(self, content):
        self.content = content
        self.clean_content = content

    async def edit(self, **kwargs):
        pass

    async def delete(self):
        pass

class MockContext:
    """Simula un commands.Context con captura de respuestas para testing."""
    def __init__(self, bot, guild: MockGuild, author: MockUser):
        self.bot = bot
        self.guild = guild
        self.author = author
        self.channel = discord.Object(id=111)
        self.message = MockMessage("!mock")
        self.invoked_subcommand = None
        # Captura de respuestas
        self.responses = []
        self.ephemeral_responses = []
        self.embeds_sent = []

    async def send(self, content=None, embed=None, ephemeral=False, **kwargs):
        msg = content or ""
        if embed:
            self.embeds_sent.append(embed)
            msg = msg or embed.description or embed.title or ""
        if ephemeral:
            self.ephemeral_responses.append(msg)
        else:
            self.responses.append(msg)
        return MockMessage(msg)

    async def reply(self, *args, **kwargs):
        return await self.send(*args, **kwargs)

    async def defer(self, ephemeral=False):
        pass

class MockMember(MockUser):
    """MockUser con propiedades de Member (roles, permisos)."""
    def __init__(self, id, name, guild, top_role_pos=10):
        super().__init__(id, name)
        self.guild = guild
        self.top_role = MockRole(id=10, position=top_role_pos)
        self.voice = None

    async def add_roles(self, role, **kwargs):
        pass

    async def remove_roles(self, role, **kwargs):
        pass

    async def send(self, *args, **kwargs):
        pass

# ============================================================
#  FIXTURES
# ============================================================

@pytest.fixture(autouse=True)
async def setup_test_db():
    """Configura la base de datos temporal antes de CADA prueba y la limpia después."""
    conn = db.get_connection()
    db.setup_database()
    
    # Insertar settings por defecto para el guild de prueba (12345)
    conn.execute(
        "INSERT OR IGNORE INTO server_settings (guild_id) VALUES (?)", (12345,)
    )
    conn.commit()
    
    yield
    
    # Limpieza: Borrar datos de todas las tablas
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    for table in tables:
        if table[0] != "sqlite_sequence":
            cursor.execute(f"DELETE FROM {table[0]};")
    conn.commit()
    # Limpiar caché
    db._settings_cache.clear()

class MyMockBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.CREAM_COLOR = discord.Color(0xFFFDD0)
        self.GEMINI_API_KEY = "test_key"
        self.http_session = None  # Se setea en fixture async si necesario

    @property
    def user(self):
        return MockUser(1234, "UmapyoiMock", bot=True)

@pytest.fixture
def mock_bot():
    return MyMockBot()

@pytest.fixture
def mock_guild():
    return MockGuild(12345, "Test Server")

@pytest.fixture
def mock_author(mock_guild):
    author = MockMember(999, "TestUser", mock_guild, top_role_pos=20)
    return author

@pytest.fixture
def mock_ctx(mock_bot, mock_guild, mock_author):
    return MockContext(mock_bot, mock_guild, mock_author)

@pytest.fixture
def mock_target(mock_guild):
    return MockMember(555, "TargetUser", mock_guild, top_role_pos=5)
