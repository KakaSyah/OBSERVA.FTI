"""
backend/config/__init__.py

Menyediakan fungsi get_config() untuk memilih kelas konfigurasi
(Development/Production) berdasarkan environment variable FLASK_ENV.
"""

import os

from backend.config.development import DevelopmentConfig
from backend.config.production import ProductionConfig

_CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}


def get_config():
    """Mengembalikan kelas konfigurasi sesuai FLASK_ENV (default: development)."""
    env = os.getenv("FLASK_ENV", "development").lower()
    return _CONFIG_MAP.get(env, DevelopmentConfig)
