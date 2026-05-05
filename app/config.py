import os
from urllib.parse import quote
from datetime import timedelta
from dotenv import load_dotenv  # ✅ Добавляем импорт

# ✅ Загружаем .env ПЕРЕД чтением переменных
load_dotenv()

class Config:
    """Конфигурация приложения"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # PostgreSQL
    DB_USER = os.environ.get('DB_USER', 'postgres')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres')
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '5432')
    DB_NAME = os.environ.get('DB_NAME', 'contract_detector')
    
    # ✅ Дебаг: выводим используемые данные (только в dev-режиме)
    if os.environ.get('FLASK_ENV') == 'development':
        print(f"🔍 [DEBUG] DB_USER: {DB_USER}")
        print(f"🔍 [DEBUG] DB_PASSWORD: {'*' * len(DB_PASSWORD)}")
        print(f"🔍 [DEBUG] DB_NAME: {DB_NAME}")
    
    # Кодируем пароль
    encoded_password = quote(DB_PASSWORD, safe='')
    
    SQLALCHEMY_DATABASE_URI = (
        f'postgresql://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
    )
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {
            'options': '-c client_encoding=UTF8',
            'sslmode': 'prefer'
        }
    }
    
    # wkhtmltopdf
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    WKHTMLTOPDF_PATH = os.path.join(PROJECT_ROOT, 'wkhtmltopdf', 'bin', 'wkhtmltopdf.exe')
    
    # Папка для загрузки
    UPLOAD_FOLDER = os.path.join(PROJECT_ROOT, 'uploads')
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)