import os
import json
import re
import tempfile
import logging
from datetime import datetime
import pdfkit
from flask import send_file
from flask import Flask, request, render_template, jsonify
import pdfplumber
from docx import Document
import os
import re
import tempfile
import logging
from datetime import datetime

import pdfkit
from flask import Flask, request, render_template, jsonify, send_file
import pdfplumber
from docx import Document

# Настройка логирования 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# конфигурация wkhtmltopdf 
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WKHTMLTOPDF_PATH = os.path.join(PROJECT_ROOT, 'wkhtmltopdf', 'bin', 'wkhtmltopdf.exe')

if not os.path.isfile(WKHTMLTOPDF_PATH):
    logger.warning(f"wkhtmltopdf не найден по пути: {WKHTMLTOPDF_PATH}")
    PDFKIT_CONFIG = None
else:
    PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)

#  Инициализация Flask
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

# Вспомогательные функции 
def secure_filename_ext(filename: str) -> str:
    """Безопасное извлечение расширения"""
    if '.' not in filename:
        return ""
    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in {'pdf', 'docx'}:
        raise ValueError("Поддерживаются только PDF и DOCX")
    return ext

def extract_text(file_path: str, ext: str) -> str:
    """Извлечение текста из PDF/DOCX"""
    try:
        if ext == 'pdf':
            with pdfplumber.open(file_path) as pdf:
                text = "\n".join(
                    page.extract_text() or "" 
                    for page in pdf.pages 
                    if page is not None
                )
        elif ext == 'docx':
            doc = Document(file_path)
            text = "\n".join(para.text for para in doc.paragraphs)
        else:
            raise ValueError("Неподдерживаемый формат")
        return re.sub(r'\s+', ' ', text).strip()
    except Exception as e:
        logger.error(f"Ошибка извлечения текста: {e}")
        raise
# Локальный анализ 
def analyze_with_local(text: str):
    """
    Улучшенный rule-based анализ договоров по ГК РФ.
    Поддерживает 10+ ключевых юридических рисков.
    """
    issues = []
    low_text = text.lower()
    # Сохраняем оригинальные строки для цитат
    lines = [line for line in text.splitlines() if line.strip()]

    # 1. Отсутствие аванса (исправлена регулярка: 30% → 30[%, ])
    if not re.search(r"(аванс|предоплата|30[%, ]|40[%, ]|50[%, ])", low_text):
        issues.append({
            "quote": "Условие об авансе не обнаружено",
            "risk": "high",
            "explanation": "Без аванса высок риск невыплаты (ст. 709 ГК РФ).",
            "suggestion": "Оплата: 50% — аванс при подписании, 50% — при сдаче результата."
        })

    # 2. Одностороннее расторжение
    if re.search(r"односторонн\w+ расторж\w+", low_text):
        for line in lines:
            if re.search(r"односторонн\w+ расторж\w+", line, re.IGNORECASE):
                issues.append({
                    "quote": line.strip(),
                    "risk": "high",
                    "explanation": "Риск потери оплаты за работу (ст. 782 ГК РФ).",
                    "suggestion": "Одностороннее расторжение — только с компенсацией расходов."
                })
                break

    # 3. Передача прав без оплаты
    has_rights = re.search(r"(исключительн\w+ прав\w+|авторск\w+ прав\w+)", low_text)
    has_payment = re.search(r"(отдельн\w+ соглашени\w+|вознаграждени\w+|оплат\w+ прав)", low_text)
    if has_rights and not has_payment:
        for line in lines:
            if re.search(r"(исключительн\w+ прав\w+|авторск\w+ прав\w+)", line, re.IGNORECASE):
                issues.append({
                    "quote": line.strip(),
                    "risk": "high",
                    "explanation": "Потеря дохода от дальнейшего использования (ст. 1234 ГК РФ).",
                    "suggestion": "Исключительные права — по отдельному соглашению после оплаты."
                })
                break

    # 4. Неопределённые сроки
    if re.search(r"в разумн\w+ срок\w+", low_text):
        for line in lines:
            if re.search(r"в разумн\w+ срок\w+", line, re.IGNORECASE):
                issues.append({
                    "quote": line.strip(),
                    "risk": "medium",
                    "explanation": "«Разумный срок» — субъективная формулировка (ст. 314 ГК РФ).",
                    "suggestion": "Замените на: «в течение 5 рабочих дней»."
                })
                break

    # 5. Отсутствие акта приёмки
    if not re.search(r"(акт приёмки|акт сдачи)", low_text):
        issues.append({
            "quote": "Порядок сдачи-приёмки не описан",
            "risk": "medium",
            "explanation": "Без акта заказчик может отказаться от оплаты.",
            "suggestion": "Результат считается принятым с момента подписания Акта."
        })

    # 6. Штрафы только для исполнителя
    client_penalty = len(re.findall(r"заказчик.*?(штраф|неустойк)", low_text))
    exec_penalty = len(re.findall(r"исполнител\w+.*?(штраф|неустойк)", low_text))
    if exec_penalty > 0 and client_penalty == 0:
        issues.append({
            "quote": "Штрафы предусмотрены только для исполнителя",
            "risk": "medium",
            "explanation": "Договор несбалансирован.",
            "suggestion": "Добавьте неустойку за просрочку оплаты (0.1%/день)."
        })

    # 7. Персональные данные без согласия (ФЗ-152)
    if (re.search(r"персональн\w+ данны\w+", low_text) and 
        not re.search(r"(согласие|фз-152|152-фз)", low_text)):
        issues.append({
            "quote": "Обработка ПДн без указания основания",
            "risk": "medium",
            "explanation": "Нарушение ФЗ-152 — штраф до 75 000 ₽.",
            "suggestion": "Добавьте: «Обработка ПДн — в соответствии с ФЗ-152»."
        })

    # 8. Безвозмездные доработки
    if re.search(r"безвозмездн\w+ (исправлен\w+|доработк\w+)", low_text):
        for line in lines:
            if re.search(r"безвозмездн\w+ (исправлен\w+|доработк\w+)", line, re.IGNORECASE):
                issues.append({
                    "quote": line.strip(),
                    "risk": "high",
                    "explanation": "Исправления при изменении ТЗ должны оплачиваться.",
                    "suggestion": "Изменения ТЗ — оплачиваются отдельно."
                })
                break

    # 9. Ответственность за третьи стороны
    if re.search(r"ответственность за (хостинг|платформ\w+|домен)", low_text):
        for line in lines:
            if re.search(r"ответственность за (хостинг|платформ\w+|домен)", line, re.IGNORECASE):
                issues.append({
                    "quote": line.strip(),
                    "risk": "high",
                    "explanation": "Вы не контролируете сбои третьих лиц.",
                    "suggestion": "Уточните: «Без ответственности за сбои хостинга/платформ»."
                })
                break

    # 10. Критически важные пропуски
    required = [
        ("предмет договора", "ст. 432 ГК РФ"),
        ("срок действия", "срок договора не указан"),
        ("инн", "отсутствуют реквизиты сторон"),
        ("подпис", "не указан порядок подписания")
    ]
    for phrase, desc in required:
        if not re.search(phrase, low_text):
            issues.append({
                "quote": f"Не найдено: «{phrase}»",
                "risk": "medium",
                "explanation": desc,
                "suggestion": "Добавьте раздел в договор."
            })
    if re.search(r"(конфиденциальн\w+ обязател\w+|nda|нда)", low_text) and \
    not re.search(r"(срок.*конфиденциальн\w+|3.*лет|пожизнен\w+)", low_text):
        issues.append({
            "quote": "Срок конфиденциальности не указан",
            "risk": "medium",
            "explanation": "Бесконечная NDA — нарушает баланс. Ст. 10 ГК РФ: недопустимо неограниченное ограничение прав.",
            "suggestion": "Укажите: «Обязательства по конфиденциальности действуют 3 года после окончания договора»."
        })
    if re.search(r"(исходн\w+ код|source code|репозиторий)", low_text) and \
    not re.search(r"(лицензия|mit|apache|право на использование)", low_text):
        for line in lines:
            if re.search(r"(исходн\w+ код|source code)", line, re.IGNORECASE):
                issues.append({
                    "quote": line.strip(),
                    "risk": "high",
                    "explanation": "Передача кода без лицензии = отказ от авторских прав (ст. 1286 ГК РФ).",
                    "suggestion": "Добавьте: «Исходный код передаётся под лицензией MIT. Право собственности сохраняется за Исполнителем»."
                })
                break
    if re.search(r"(оплата.*после|постоплата|оплата при принятии)", low_text) and \
    not re.search(r"(10|15|20|30)\s*дн\w+", low_text):
        issues.append({
            "quote": "Срок оплаты не ограничен",
            "risk": "medium",
            "explanation": "Отсрочка >30 дней — риск просрочки. Ст. 314 ГК РФ: разумный срок — до 7 дней, иное — по договору.",
            "suggestion": "Уточните: «Оплата в течение 10 рабочих дней после подписания Акта»."
        })
    if re.search(r"(программн\w+ продукт|сайт|приложен\w+)", low_text) and \
    not re.search(r"(гаранти\w+ срок|исправление ошибок|багфикс)", low_text):
        issues.append({
            "quote": "Гарантийный срок не предусмотрен",
            "risk": "medium",
            "explanation": "Без гарантии — заказчик может требовать правки вечно. Ст. 723 ГК РФ: гарантия устанавливается по умолчанию.",
            "suggestion": "Добавьте: «Гарантийный срок — 30 дней. В течение него — бесплатное устранение ошибок»."
        })
    if re.search(r"(изменение тз|правки|корректировки)", low_text) and \
    not re.search(r"(допсоглашен\w+|письменн\w+ согласован\w+|оцениваетс\w+ отдельно)", low_text):
        issues.append({
            "quote": "Изменения ТЗ не регламентированы",
            "risk": "high",
            "explanation": "Заказчик может бесконечно менять требования без оплаты.",
            "suggestion": "Укажите: «Изменения ТЗ оформляются допсоглашением с расчётом стоимости и сроков»."
        })
    if re.search(r"(налоги исполнител\w+|ндфл|взносы.*исполнител\w+)", low_text):
        for line in lines:
            if re.search(r"налоги исполнител\w+", line, re.IGNORECASE):
                issues.append({
                    "quote": line.strip(),
                    "risk": "high",
                    "explanation": "Если вы ИП — налоги платите сами. Условие о перечислении НДФЛ — признак трудового договора (ст. 15 ТК РФ).",
                    "suggestion": "Удалите: «Исполнитель самостоятельно исполняет обязанности налогоплательщика»."
                })
                break
    if re.search(r"(конкурент\w+|аналогичн\w+ услуг\w+|иные заказчики)", low_text) and \
    re.search(r"(запрещает|не имеет права|обязуется не)", low_text):
        for line in lines:
            if re.search(r"конкурент\w+", line, re.IGNORECASE):
                issues.append({
                    "quote": line.strip(),
                    "risk": "high",
                    "explanation": "Запрет на работу с конкурентами — ограничение свободы труда (ст. 37 Конституции).",
                    "suggestion": "Замените на: «Во время действия договора — без права работы с прямым конкурентом по данному проекту»."
                })
                break
    if not re.search(r"(арбитражн\w+ суд|судебн\w+ порядок|претензионн\w+ порядок)", low_text):
        issues.append({
            "quote": "Порядок разрешения споров не указан",
            "risk": "medium",
            "explanation": "Без претензионного порядка — сложнее взыскать долг. Ст. 4 АПК РФ: претензия — обязательна для коммерческих споров.",
            "suggestion": "Добавьте: «Споры разрешаются после направления претензии в течение 10 дней»."
        })
    if re.search(r"(автоматическ\w+ продлен\w+|продлеваетс\w+ автоматически)", low_text):
        for line in lines:
            if re.search(r"автоматическ\w+ продлен\w+", line, re.IGNORECASE):
                issues.append({
                    "quote": line.strip(),
                    "risk": "medium",
                    "explanation": "Автопродление без уведомления — нарушает ст. 450 ГК РФ (изменение договора по соглашению).",
                    "suggestion": "Уточните: «Договор продлевается, если ни одна из сторон не уведомила о расторжении за 14 дней»."
                })
                break
    if re.search(r"(сопровожден\w+|техподдержка|хостинг.*после передачи)", low_text) and \
    not re.search(r"(отдельн\w+ договор|возмездн\w+|стоимость)", low_text):
        issues.append({
            "quote": "Техподдержка без оплаты",
            "risk": "medium",
            "explanation": "Бесплатное сопровождение = скрытая работа за свой счёт.",
            "suggestion": "Добавьте: «Техническая поддержка — по отдельному возмездному договору»."
        })
    if re.search(r"(100%.*аванс|полная предоплата)", low_text) and \
    not re.search(r"(возврат аванса|гарантийное письмо|обеспечительн\w+ платеж)", low_text):
        issues.append({
            "quote": "100% аванс без гарантий возврата",
            "risk": "medium",
            "explanation": "Если вы не выполните работу — заказчик потребует возврат. Ст. 381 ГК РФ: обеспечительные меры снижают риски.",
            "suggestion": "Добавьте: «Аванс возвращается в случае неисполнения по вине Исполнителя»."
        })
    if not re.search(r"(форс-мажор|непреодолим\w+ сил\w+|обстоятельств\w+ непреодолим\w+ сил\w+)", low_text):
        issues.append({
            "quote": "Условие о форс-мажоре отсутствует",
            "risk": "medium",
            "explanation": "Без форс-мажора — вы несёте ответственность за срыв сроков из-за ЧС, блокировок и т.п. (ст. 401 ГК РФ).",
            "suggestion": "Добавьте: «Стороны освобождаются от ответственности при форс-мажоре (эпидемии, блокировки, сбои госуслуг)»."
        })
    if re.search(r"(портфолио|демонстрац\w+|публикац\w+)", low_text) and \
    not re.search(r"(согласие исполнител\w+|письменн\w+ разрешен\w+)", low_text):
        issues.append({
            "quote": "Публикация работ без согласия",
            "risk": "low",
            "explanation": "Нарушает право на авторство (ст. 1228 ГК РФ).",
            "suggestion": "Добавьте: «Публикация в портфолио — с письменного согласия Исполнителя»."
        })
    exec_fine = len(re.findall(r"(исполнител\w+.*неустойк|штраф.*исполнител\w+)", low_text))
    client_fine = len(re.findall(r"(заказчик.*неустойк|штраф.*заказчик\w+)", low_text))
    if exec_fine > 0 and client_fine == 0:
        issues.append({
            "quote": "Неустойка предусмотрена только для исполнителя",
            "risk": "medium",
            "explanation": "Нарушает баланс прав (ст. 10 ГК РФ).",
            "suggestion": "Добавьте: «За просрочку оплаты — неустойка 0.1% от суммы за каждый день»."
        })
    if re.search(r"(исполнител\w+.*ип)", low_text) and \
    not re.search(r"(отказ от договора|односторонний отказ|ст\. 32 зозпп)", low_text):
        issues.append({
            "quote": "Нет права на односторонний отказ",
            "risk": "medium",
            "explanation": "Если вы ИП и услуга для физлица — вы вправе отказаться по ст. 32 ЗоЗПП.",
            "suggestion": "Добавьте: «Исполнитель вправе отказаться от договора, компенсировав фактические расходы»."
        })
    if re.search(r"(пдн третьих лиц|данные клиентов заказчика|база контактов)", low_text) and \
    not re.search(r"(оператор пдн|заказчик — оператор|согласие субъектов)", low_text):
        issues.append({
            "quote": "Обработка ПДн третьих лиц без основания",
            "risk": "high",
            "explanation": "Вы не можете обрабатывать данные, если не оператор. ФЗ-152, ст. 6.",
            "suggestion": "Уточните: «Заказчик гарантирует наличие согласий субъектов ПДн. Исполнитель — не оператор»."
        })
    #  РАСЧЁТ РЕЙТИНГА 
    score = 100
    for issue in issues:
        score -= 20 if issue["risk"] == "high" else 10
    score = max(0, score)

    #  ИТОГОВЫЙ ВЫВОД 
    if not issues:
        summary = " Договор безопасен. Критических рисков не обнаружено."
    else:
        high = sum(1 for i in issues if i["risk"] == "high")
        medium = sum(1 for i in issues if i["risk"] == "medium")
        parts = []
        if high: parts.append(f"{high} критичных")
        if medium: parts.append(f"{medium} спорных")
        summary = f"Обнаружено: {', '.join(parts)}. Обратите внимание на  критичные риски."

    return {
        "issues": issues,
        "summary": summary,
        "meta": {
            "source": "local",
            "score": score,  
            "rules_applied": 10
        }
    }
#  Роуты 
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "Файл не загружен"}), 400
        file = request.files['file']
        if not file.filename:
            return jsonify({"error": "Пустое имя файла"}), 400

        ext = secure_filename_ext(file.filename)

        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            file.save(tmp.name)
            temp_path = tmp.name

        try:
            text = extract_text(temp_path, ext)
            if not text.strip():
                return jsonify({"error": "Не удалось извлечь текст — проверьте файл"}), 400


            result = analyze_with_local(text)  
            return jsonify(result)

        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    except Exception as e:
        logger.exception("Ошибка в /analyze")
        return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500
@app.route('/health')
def health():
    return jsonify({"status": "ok", "local_mode": True})
@app.route('/download-pdf', methods=['POST'])
def download_pdf():
    try:
        data = request.get_json()
        if not data or 'issues' not in data or 'summary' not in data or 'meta' not in data:
            return jsonify({"error": "Недостаточно данных для генерации PDF"}), 400

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

        #  передаём конфигурацию
        pdfkit.from_string(
            html,
            pdf_path,
            options=options,
            configuration=PDFKIT_CONFIG 
        )

        return send_file(pdf_path, as_attachment=True, download_name="analiz_dogovora.pdf")

    except Exception as e:
        logger.exception("Ошибка при генерации PDF")
        return jsonify({"error": f"Не удалось создать PDF: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5001))
    logger.info(f"Запуск локального Contract Clause Detector на порту {port}")
    app.run(debug=False, host='0.0.0.0', port=port)