import os
from flask import Flask, session, request, jsonify, redirect, url_for
from .config import Config
from .models import init_db, login_manager, db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(config_class=Config):
    # ✅ Вычисляем абсолютный путь к корню проекта
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # ✅ Создаём Flask с путями относительно корня проекта
    app = Flask(__name__,
                template_folder=os.path.join(PROJECT_ROOT, 'templates'),
                static_folder=os.path.join(PROJECT_ROOT, 'static'),
                static_url_path='/static')
    
    app.config.from_object(config_class)
    app.config['UPLOAD_FOLDER'] = Config.UPLOAD_FOLDER
    
    # Инициализация БД и LoginManager
    init_db(app)
    
    # Настройка перенаправления
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    
    # Регистрация blueprints (БЕЗ template_folder!)
    from .routes.main import main_bp
    from .routes.auth import auth_bp
    
    app.register_blueprint(main_bp)  # ✅ Blueprint наследует пути от app
    app.register_blueprint(auth_bp)
    
    # Контекст-процессоры
    @app.context_processor
    def inject_theme():
        theme = session.get('user_theme', 'light')
        return {'current_theme': theme}
    
    @app.context_processor
    def inject_user():
        from flask_login import current_user
        return {'current_user': current_user}
    
    # Обработчик 401
    @app.errorhandler(401)
    def unauthorized(error):
        if request.path.startswith('/api') or request.is_json:
            return jsonify({'error': 'Требуется авторизация'}), 401
        return redirect(url_for('auth.login', next=request.url))
    
    logger.info("Приложение создано успешно")
    logger.info(f"📁 Templates: {app.template_folder}")
    logger.info(f"📁 Static: {app.static_folder}")
    return app