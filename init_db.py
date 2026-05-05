import sys
import os
from dotenv import load_dotenv

load_dotenv()

if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from app import create_app
from app.config import Config
from app.models import db, User

def init_database():
    """Создание БД и таблиц"""
    print("Инициализация приложения...")
    
    db_password = os.environ.get('DB_PASSWORD', 'postgres')
    print(f" [DEBUG] Используемый пароль: {'*' * len(db_password)} (длина: {len(db_password)})")
    
    app = create_app(Config)
    
    print(f" URI БД: {app.config['SQLALCHEMY_DATABASE_URI'][:60]}...")
    
    with app.app_context():
        try:
            print("Создание таблиц...")
            db.create_all()
            print("Таблицы созданы успешно!")
            
            if not User.query.filter_by(email='admin@example.com').first():
                print("Создание тестового пользователя...")
                admin = User(
                    username='admin',
                    email='admin@example.com',
                    theme='light'
                )
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
                print("Тестовый пользователь создан:")
                print("   Email: admin@example.com")
                print("   Пароль: admin123")
            else:
                print("Тестовый пользователь уже существует")
                
        except Exception as e:
            db.session.rollback()
            print(f"Ошибка при инициализации БД: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise

if __name__ == '__main__':
    init_database()