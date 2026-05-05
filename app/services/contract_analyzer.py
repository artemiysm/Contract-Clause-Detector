import re
import logging
import pdfplumber
from docx import Document

logger = logging.getLogger(__name__)

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

def analyze_contract(text: str) -> dict:
    """
    Анализ договора на риски
    """
    issues = []
    low_text = text.lower()
    lines = [line for line in text.splitlines() if line.strip()]

    # 1. Отсутствие аванса
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
    
    # Дополнительные проверки
    if re.search(r"(конфиденциальн\w+ обязател\w+|nda|нда)", low_text) and \
    not re.search(r"(срок.*конфиденциальн\w+|3.*лет|пожизнен\w+)", low_text):
        issues.append({
            "quote": "Срок конфиденциальности не указан",
            "risk": "medium",
            "explanation": "Бесконечная NDA — нарушает баланс.",
            "suggestion": "Укажите: «Обязательства по конфиденциальности действуют 3 года»."
        })

    # РАСЧЁТ РЕЙТИНГА 
    score = 100
    for issue in issues:
        score -= 20 if issue["risk"] == "high" else 10
    score = max(0, score)

    # ИТОГОВЫЙ ВЫВОД 
    if not issues:
        summary = "Договор безопасен. Критических рисков не обнаружено."
    else:
        high = sum(1 for i in issues if i["risk"] == "high")
        medium = sum(1 for i in issues if i["risk"] == "medium")
        parts = []
        if high: parts.append(f"{high} критичных")
        if medium: parts.append(f"{medium} спорных")
        summary = f"Обнаружено: {', '.join(parts)}. Обратите внимание на критичные риски."

    return {
        "issues": issues,
        "summary": summary,
        "meta": {
            "source": "local",
            "score": score,  
            "rules_applied": 10
        }
    }