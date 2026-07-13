"""
backend/config/development.py

Override konfigurasi khusus untuk environment development/local.
"""

from backend.config.base import BaseConfig


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # HTTP lokal biasanya tanpa HTTPS
