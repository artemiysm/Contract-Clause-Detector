from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, flash, send_file, current_app
from flask_login import login_required, current_user
from ..services.contract_analyzer import analyze_contract, secure_filename_ext, extract_text
from ..utils.pdf_generator import generate_pdf
from ..config import Config
from ..models import db, User, Contract
import pdfkit
import logging
from datetime import datetime
import os
import tempfile
import uuid

logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)


# ================= ПУБЛИЧНЫЕ РОУТЫ =================

@main_bp.route('/')
def index():
    """Главная страница — доступна всем"""
    return render_template('index.html')

@main_bp.route('/health')
def health():
    """Health check для мониторинга"""
    return jsonify({"status": "ok", "local_mode": True})


# ================= ЗАЩИЩЁННЫЕ РОУТЫ (ТРЕБУЮТ АВТОРИЗАЦИИ) =================

@main_bp.route('/lk')
@login_required
def dashboard():
    """Личный кабинет — главная страница ЛК"""
    user_contracts = Contract.query.filter_by(user_id=current_user.id).all()
    contracts_count = len(user_contracts)
    
    # Подсчёт рисков
    total_risks = 0
    for c in user_contracts:
        if c.analysis_result and 'issues' in c.analysis_result:
            total_risks += len(c.analysis_result['issues'])
    
    stats = {
        "total_checks": contracts_count,
        "total_risks": total_risks,
        "remaining": max(0, 15 - contracts_count),
        "limit": 15,
        "time_saved": "~4 ч.",
        "plan": "Стандарт" if contracts_count < 15 else "Премиум"
    }
    
    # Формирование истории (последние 10)
    history = []
    for contract in sorted(user_contracts, key=lambda x: x.uploaded_at, reverse=True)[:10]:
        risk_level = 'success'
        risk_label = 'Без рисков'
        
        if contract.analysis_result and 'issues' in contract.analysis_result:
            issues = contract.analysis_result['issues']
            high_risks = sum(1 for i in issues if i.get('risk') == 'high')
            medium_risks = sum(1 for i in issues if i.get('risk') == 'medium')
            
            if high_risks > 0:
                risk_level = 'danger'
                risk_label = 'Высокий риск'
            elif medium_risks > 0:
                risk_level = 'warning'
                risk_label = 'Средний риск'
        
        history.append({
            "id": contract.id,
            "filename": contract.filename,
            "type": "Договор",
            "date": contract.uploaded_at.strftime("%d.%m.%Y"),
            "risk_class": risk_level,
            "risk_label": risk_label
        })
    
    return render_template('lk.html', active_page='dashboard', stats=stats, history=history)

@main_bp.route('/contracts')
@login_required
def contracts():
    """Мои договоры — список всех файлов"""
    user_contracts = Contract.query.filter_by(
        user_id=current_user.id
    ).order_by(Contract.uploaded_at.desc()).all()
    
    # Формируем данные для шаблона
    contracts_data = []
    for contract in user_contracts:
        risk_level = 'success'
        risk_label = 'Без рисков'
        
        if contract.analysis_result and 'issues' in contract.analysis_result:
            issues = contract.analysis_result['issues']
            high_risks = sum(1 for i in issues if i.get('risk') == 'high')
            medium_risks = sum(1 for i in issues if i.get('risk') == 'medium')
            
            if high_risks > 0:
                risk_level = 'danger'
                risk_label = 'Высокий риск'
            elif medium_risks > 0:
                risk_level = 'warning'
                risk_label = 'Средний риск'
        
        contracts_data.append({
            "id": contract.id,
            "filename": contract.filename,
            "type": contract.file_type.upper(),
            "date": contract.uploaded_at.strftime("%d.%m.%Y %H:%M"),
            "risk_class": risk_level,
            "risk_label": risk_label,
            "score": contract.analysis_result.get('meta', {}).get('score', 0) if contract.analysis_result else 0
        })
    
    return render_template('contracts.html', contracts=contracts_data)

@main_bp.route('/billing')
@login_required
def billing():
    contracts_count = Contract.query.filter_by(user_id=current_user.id).count()
    
    # ✅ Вычисляем процент заранее
    limit = 15
    usage_percent = (contracts_count / limit * 100) if limit > 0 else 0
    
    stats = {
        "total_checks": contracts_count,
        "total_risks": 0,
        "remaining": max(0, limit - contracts_count),
        "limit": limit,
        "time_saved": "~4 ч.",
        "plan": "Стандарт" if contracts_count < limit else "Премиум",
        "usage_percent": round(usage_percent, 1)  # ✅ Добавляем процент
    }
    return render_template('billing.html', stats=stats)

@main_bp.route('/billing/subscribe', methods=['POST'])
@login_required
def subscribe():
    """Обработка перехода на премиум"""
    flash("Запрос на переход в Премиум отправлен! (Демо)", "success")
    return redirect(url_for('main.billing'))

@main_bp.route('/settings')
@login_required
def settings():
    """Настройки — перенаправляем на профиль"""
    return redirect(url_for('auth.profile'))

@main_bp.route('/report/<int:report_id>')
@login_required
def view_report(report_id):
    """Просмотр отчёта по конкретному договору"""
    contract = Contract.query.get_or_404(report_id)
    
    # Проверка: пользователь может смотреть только свои договоры
    if contract.user_id != current_user.id:
        flash('У вас нет доступа к этому договору', 'error')
        return redirect(url_for('main.dashboard'))
    
    # Извлечение данных из JSON-результата
    analysis = contract.analysis_result or {}
    
    return render_template(
        'report.html',
        summary=analysis.get('summary', ''),
        score=analysis.get('meta', {}).get('score', 0),
        issues=analysis.get('issues', []),
        timestamp=contract.uploaded_at.strftime("%d.%m.%Y %H:%M")
    )

@main_bp.route('/analyze', methods=['POST'])
@login_required
def analyze():
    """Загрузка и анализ договора"""
    try:
        # Проверка файла
        if 'file' not in request.files:
            return jsonify({"error": "Файл не загружен"}), 400
        
        file = request.files['file']
        if not file.filename:
            return jsonify({"error": "Пустое имя файла"}), 400

        # Валидация расширения
        ext = secure_filename_ext(file.filename)
        
        # Генерация уникального имени и пути
        unique_filename = f"{uuid.uuid4()}.{ext}"
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)

        # Временное сохранение для обработки
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            file.save(tmp.name)
            temp_path = tmp.name

        try:
            # Извлечение текста
            text = extract_text(temp_path, ext)
            if not text.strip():
                return jsonify({"error": "Не удалось извлечь текст — проверьте файл"}), 400

            # Анализ
            result = analyze_contract(text)
            
            # Сохранение в БД
            contract = Contract(
                filename=file.filename,
                file_path=file_path,
                file_type=ext,
                analysis_result=result,
                user_id=current_user.id
            )
            
            # Перемещение файла в постоянное хранилище
            os.rename(temp_path, file_path)
            
            db.session.add(contract)
            db.session.commit()
            
            return jsonify(result)

        except Exception as e:
            # Очистка временного файла при ошибке
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise e

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Критическая ошибка в /analyze")
        return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500

@main_bp.route('/download-pdf', methods=['POST'])
@login_required
def download_pdf():
    """Генерация и скачивание PDF-отчёта"""
    try:
        data = request.get_json()
        
        # Проверка наличия ключей
        if not data or 'issues' not in data or 'summary' not in data or 'meta' not in data:
            return jsonify({"error": "Недостаточно данных для генерации PDF"}), 400

        # Настройка wkhtmltopdf
        config = None
        if os.path.isfile(Config.WKHTMLTOPDF_PATH):
            config = pdfkit.configuration(wkhtmltopdf=Config.WKHTMLTOPDF_PATH)

        # Генерация
        pdf_path = generate_pdf(data, config)
        
        return send_file(
            pdf_path, 
            as_attachment=True, 
            download_name="analiz_dogovora.pdf",
            mimetype='application/pdf'
        )

    except FileNotFoundError:
        logger.error("wkhtmltopdf не найден")
        return jsonify({"error": "wkhtmltopdf не установлен. Проверьте путь в конфиге."}), 500
    except Exception as e:
        logger.exception("Ошибка при генерации PDF")
        return jsonify({"error": f"Не удалось создать PDF: {str(e)}"}), 500