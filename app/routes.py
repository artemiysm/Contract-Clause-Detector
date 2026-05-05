from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, flash, send_file
from .services.contract_analyzer import analyze_contract
from .utils.pdf_generator import generate_pdf
from .config import Config
import pdfkit
import logging
from datetime import datetime
import os
import tempfile

logger = logging.getLogger(__name__)

# ✅ ИСПРАВЛЕНО: добавлен template_folder='../templates'
main_bp = Blueprint('main', __name__, 
                   template_folder='../templates',
                   static_folder='../static', 
                   static_url_path='/static')

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/lk')
def dashboard():
    stats = {
        "total_checks": 12,
        "total_risks": 5,
        "remaining": 3,
        "limit": 15,
        "time_saved": "4 ч ~ 20 000 р.",
        "plan": "Стандарт"
    }
    history = [
        {"id": 1, "filename": "Трудовой договор_Иванов.pdf", "type": "Трудовой договор", "date": "24.05.2024", "risk_class": "danger", "risk_label": "Высокий риск"},
        {"id": 2, "filename": "Договор аренды квартиры.docx", "type": "Аренда", "date": "22.05.2024", "risk_class": "warning", "risk_label": "Средний риск"},
        {"id": 3, "filename": "ДКП Автомобиль.pdf", "type": "Купля-продажа", "date": "20.05.2024", "risk_class": "success", "risk_label": "Без рисков"},
    ]
    return render_template('lk.html', active_page='dashboard', stats=stats, history=history)

@main_bp.route('/contracts')
def contracts():
    stats = {"total_checks": 12, "total_risks": 5, "remaining": 3, "limit": 15, "time_saved": "~4 ч.", "plan": "Стандарт"}
    return render_template('lk.html', active_page='contracts', stats=stats, history=[])

@main_bp.route('/billing')
def billing():
    stats = {"total_checks": 12, "total_risks": 5, "remaining": 3, "limit": 15, "time_saved": "~4 ч.", "plan": "Стандарт"}
    return render_template('lk.html', active_page='billing', stats=stats, history=[])

@main_bp.route('/billing/subscribe', methods=['POST'])
def subscribe():
    flash("Запрос на переход в Премиум отправлен! (Демо)", "success")
    return redirect(url_for('main.billing'))

@main_bp.route('/settings')
def settings():
    stats = {"total_checks": 12, "total_risks": 5, "remaining": 3, "limit": 15, "time_saved": "~4 ч.", "plan": "Стандарт"}
    return render_template('lk.html', active_page='settings', stats=stats, history=[])

@main_bp.route('/settings/update', methods=['POST'])
def update_settings():
    username = request.form.get('username')
    email = request.form.get('email')
    theme = request.form.get('theme', 'light')
    
    logger.info(f"Настройки обновлены: username={username}, email={email}, theme={theme}")
    
    session['user_theme'] = theme
    session['username'] = username
    
    flash("Настройки успешно сохранены", "success")
    return redirect(url_for('main.settings'))

@main_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.index'))

@main_bp.route('/report/<int:report_id>')
def view_report(report_id):
    return render_template('report.html', 
                           summary=f"Демо-отчёт для договора #{report_id}", 
                           score=85, 
                           issues=[], 
                           timestamp=datetime.now().strftime("%d.%m.%Y %H:%M"))

@main_bp.route('/analyze', methods=['POST'])
def analyze():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "Файл не загружен"}), 400
        file = request.files['file']
        if not file.filename:
            return jsonify({"error": "Пустое имя файла"}), 400

        from .services.contract_analyzer import secure_filename_ext, extract_text
        
        ext = secure_filename_ext(file.filename)

        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            file.save(tmp.name)
            temp_path = tmp.name

        try:
            text = extract_text(temp_path, ext)
            if not text.strip():
                return jsonify({"error": "Не удалось извлечь текст — проверьте файл"}), 400

            result = analyze_contract(text)  
            return jsonify(result)

        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    except Exception as e:
        logger.exception("Ошибка в /analyze")
        return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500

@main_bp.route('/health')
def health():
    return jsonify({"status": "ok", "local_mode": True})

@main_bp.route('/download-pdf', methods=['POST'])
def download_pdf():
    try:
        data = request.get_json()
        # ✅ ИСПРАВЛЕНО: добавлено 'data' в конце условия
        if not data or 'issues' not in data or 'summary' not in data or 'meta' not in data:
            return jsonify({"error": "Недостаточно данных для генерации PDF"}), 400

        config = None
        if os.path.isfile(Config.WKHTMLTOPDF_PATH):
            config = pdfkit.configuration(wkhtmltopdf=Config.WKHTMLTOPDF_PATH)

        pdf_path = generate_pdf(data, config)
        return send_file(pdf_path, as_attachment=True, download_name="analiz_dogovora.pdf")

    except Exception as e:
        logger.exception("Ошибка при генерации PDF")
        return jsonify({"error": f"Не удалось создать PDF: {str(e)}"}), 500