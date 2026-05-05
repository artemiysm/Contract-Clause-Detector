import pdfkit
from flask import render_template
import tempfile
import os
from datetime import datetime

def generate_pdf(data: dict, config=None):
    """
    Генерация PDF отчёта
    
    Args:
        data: Данные для отчёта (issues, summary, meta)
        config: Конфигурация pdfkit
    
    Returns:
        str: Путь к сгенерированному PDF файлу
    """
    context = {
        "issues": data["issues"],
        "summary": data["summary"],
        "score": data["meta"]["score"],
        "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    
    html = render_template('report.html', **context)
    
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = tmp.name
    
    options = {
        'page-size': 'A4',
        'margin-top': '0.75in',
        'margin-right': '0.75in',
        'margin-bottom': '0.75in',
        'margin-left': '0.75in',
        'encoding': "UTF-8",
        'no-outline': None,
        'enable-local-file-access': ''
    }
    
    pdfkit.from_string(html, pdf_path, options=options, configuration=config)
    return pdf_path