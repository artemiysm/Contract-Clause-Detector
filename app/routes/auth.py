from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from ..models import db, User
from flask_login import login_user, logout_user, login_required, current_user
import logging
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db

from werkzeug.security import generate_password_hash, check_password_hash
logger = logging.getLogger(__name__)
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Регистрация пользователя"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        theme = request.form.get('theme', 'light')
        
        # Валидация
        errors = []
        if not username or len(username) < 3:
            errors.append('Имя пользователя должно содержать минимум 3 символа')
        if not email or '@' not in email:
            errors.append('Введите корректный email')
        if not password or len(password) < 6:
            errors.append('Пароль должен содержать минимум 6 символов')
        if password != confirm_password:
            errors.append('Пароли не совпадают')
        
        # Проверка на существующего пользователя
        if User.query.filter_by(email=email).first():
            errors.append('Пользователь с таким email уже существует')
        if User.query.filter_by(username=username).first():
            errors.append('Пользователь с таким именем уже существует')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('auth/register.html', username=username, email=email, theme=theme)
        
        # Создание пользователя
        user = User(username=username, email=email, theme=theme)
        user.set_password(password)
        
        try:
            db.session.add(user)
            db.session.commit()
            flash('Регистрация успешна! Теперь вы можете войти.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка при регистрации: {e}")
            flash('Произошла ошибка при регистрации. Попробуйте позже.', 'error')
    
    return render_template('auth/register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Вход пользователя"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Аккаунт деактивирован. Обратитесь к администрации.', 'error')
                return render_template('auth/login.html')
            
            login_user(user, remember=remember)
            session['user_theme'] = user.theme
            
            # Редирект на страницу, с которой перешли, или в ЛК
            next_page = request.args.get('next')
            flash(f'С возвращением, {user.username}!', 'success')
            return redirect(next_page if next_page and next_page.startswith('/') else url_for('main.dashboard'))
        else:
            flash('Неверный email или пароль', 'error')
    
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """Выход пользователя"""
    logout_user()
    session.clear()
    flash('Вы успешно вышли из системы', 'info')
    return redirect(url_for('main.index'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        # === Обработка смены темы ===
        if 'theme' in request.form:
            theme = request.form.get('theme')
            if theme in ['light', 'dark', 'auto']:
                current_user.theme = theme
                db.session.commit()
                flash('Тема оформления обновлена!', 'success')
            return redirect(url_for('auth.profile'))
        
        # === Обработка смены пароля ===
        if 'current_password' in request.form:
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            # Валидация
            if not check_password_hash(current_user.password_hash, current_password):
                flash('Неверный текущий пароль', 'error')
            elif len(new_password) < 6:
                flash('Новый пароль должен содержать минимум 6 символов', 'error')
            elif new_password != confirm_password:
                flash('Пароли не совпадают', 'error')
            else:
                current_user.password_hash = generate_password_hash(new_password)
                db.session.commit()
                flash('Пароль успешно изменён!', 'success')
            return redirect(url_for('auth.profile'))
        
        # === Обработка 2FA ===
        if 'two_factor_enabled' in request.form:
            current_user.two_factor_enabled = request.form.get('two_factor_enabled') == 'on'
            db.session.commit()
            flash('Настройки двухфакторной аутентификации обновлены', 'success')
            return redirect(url_for('auth.profile'))
    
    return render_template('auth/profile.html')