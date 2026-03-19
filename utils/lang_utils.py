import json
import os
from typing import Any, Dict, Optional

class TranslationManager:
    _instance = None
    _locales: Dict[str, Dict[str, Any]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TranslationManager, cls).__new__(cls)
            cls._instance._load_all_locales()
        return cls._instance

    def _load_all_locales(self):
        locales_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'locales')
        if not os.path.exists(locales_dir):
            return

        for filename in os.listdir(locales_dir):
            if filename.endswith('.json'):
                lang_code = filename[:-5]
                try:
                    with open(os.path.join(locales_dir, filename), 'r', encoding='utf-8') as f:
                        self._locales[lang_code] = json.load(f)
                except Exception as e:
                    print(f"Error loading locale {lang_code}: {e}")

    def get(self, key: str, lang: str = 'es', **kwargs) -> str:
        """
        Obtiene una traducción para la clave dada en el idioma especificado.
        Soporta claves anidadas con puntos (ej: 'economy.balance.title').
        """
        keys = key.split('.')
        data = self._locales.get(lang, self._locales.get('es', {}))
        
        result = data
        for k in keys:
            if isinstance(result, dict) and k in result:
                result = result[k]
            else:
                # Fallback a español si no existe en el idioma actual
                if lang != 'es':
                    return self.get(key, lang='es', **kwargs)
                return key # Retornar la clave si no se encuentra nada

        if isinstance(result, str):
            try:
                return result.format(**kwargs)
            except KeyError:
                return result
        return str(result)

# Instancia global para importación fácil
translator = TranslationManager()

def _t(key: str, lang: str = 'es', **kwargs) -> str:
    return translator.get(key, lang, **kwargs)
