"""
backend/config/production.py

Override konfigurasi khusus untuk environment production.
Seluruh pengaturan keamanan diperketat di sini.
"""

from backend.config.base import BaseConfig


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Strict"
