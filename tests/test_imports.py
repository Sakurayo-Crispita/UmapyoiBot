"""Tests para verificar que todos los módulos se importan correctamente (sin errores de sintaxis)."""
import pytest
import importlib
import os


class TestCogImports:
    """Verifica que cada cog se importa sin SyntaxError ni ImportError."""

    def _get_cog_names(self):
        cogs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cogs")
        return [f[:-3] for f in os.listdir(cogs_dir) if f.endswith(".py") and not f.startswith("_")]

    def test_all_cogs_importable(self):
        failures = []
        for cog_name in self._get_cog_names():
            try:
                importlib.import_module(f"cogs.{cog_name}")
            except Exception as e:
                failures.append(f"cogs.{cog_name}: {type(e).__name__}: {e}")

        if failures:
            pytest.fail("Los siguientes cogs fallaron al importar:\n" + "\n".join(failures))

    def test_individual_cog_has_setup(self):
        """Cada cog debe tener una función setup() para discord.py."""
        for cog_name in self._get_cog_names():
            mod = importlib.import_module(f"cogs.{cog_name}")
            assert hasattr(mod, 'setup'), f"El cog '{cog_name}' no tiene función setup()"


class TestUtilImports:
    """Verifica que los módulos utils se importan correctamente."""

    def test_database_manager(self):
        from utils import database_manager
        assert hasattr(database_manager, 'setup_database')
        assert hasattr(database_manager, 'get_balance')

    def test_api_helpers(self):
        from utils import api_helpers
        assert hasattr(api_helpers, 'ask_gemini')
        assert hasattr(api_helpers, 'search_anime')

    def test_lang_utils(self):
        from utils import lang_utils
        assert hasattr(lang_utils, '_t')

    def test_constants(self):
        from utils import constants
        assert hasattr(constants, 'WANTED_TEMPLATE_URL')
