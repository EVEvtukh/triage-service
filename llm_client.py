"""
llm_client.py — обёртка над LLM для классификации обращения и черновика ответа.

Правила (см. системный промпт ниже):
- отвечать строго по входному тексту, не выдумывать факты;
- если данных мало / текст неоднозначный -> confidence=low, escalate=true;
- отвечать СТРОГО в JSON-формате.

Если LLM недоступна / вернула не-JSON / произошла любая ошибка —
срабатывает fallback: escalate=true + шаблонный draft_reply.
Это и есть сценарий "если всё сломалось".
"""
import json
import os

ALLOWED_CATEGORIES = {"billing", "support", "complaint", "other"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}

# Контекст: система повышения квалификации педагогических работников
SYSTEM_PROMPT = """Ты — ассистент службы поддержки системы дополнительного
профессионального образования (курсы повышения квалификации и
переподготовки для педагогических работников).

Твоя задача: по тексту обращения слушателя курса
1) определить категорию обращения,
2) написать короткий черновик ответа для оператора.

Категории (выбери ровно одну):
- billing — оплата курса, счета, возврат средств, реквизиты, скидки, акты;
- support — технические и организационные вопросы: вход в личный кабинет,
  доступ к материалам, сроки обучения, получение удостоверения/сертификата,
  расписание, тестирование;
- complaint — жалобы: на качество курса, лектора, задержки, ошибки в
  документах, недовольство сервисом;
- other — всё, что не подходит под три категории выше.

Жёсткие правила:
1. Отвечай строго по тексту обращения. Не придумывай факты, даты, суммы,
   номера заказов или условия, которых нет во входном тексте.
2. Если текста мало, он неоднозначен или требует данных, которых у тебя
   нет (например, точный статус оплаты в системе) — ставь
   confidence="low" и escalate=true.
3. draft_reply — 1-6 предложений, вежливый нейтральный тон, без обещаний,
   которые не подтверждены входным текстом (например, не называй точные
   сроки возврата денег, если это не в тексте).
4. Верни ОТВЕТ СТРОГО В ФОРМАТЕ JSON, без пояснений и без markdown,
   ровно такими полями:
{"category": "billing|support|complaint|other",
 "draft_reply": "текст черновика ответа",
 "confidence": "high|medium|low",
 "escalate": true|false}
"""

FALLBACK_REPLY = (
    "Спасибо за обращение! Ваш запрос передан оператору поддержки, "
    "он свяжется с вами в ближайшее время."
)


def _fallback_result(error_message: str) -> dict:
    return {
        "category": "other",
        "draft_reply": FALLBACK_REPLY,
        "confidence": "low",
        "escalate": True,
        "error": error_message,
    }


def _validate_and_normalize(data: dict) -> dict:
    """Проверяем, что модель не 'сломала' формат ответа."""
    category = data.get("category")
    confidence = data.get("confidence")
    draft_reply = data.get("draft_reply")
    escalate = data.get("escalate")

    if category not in ALLOWED_CATEGORIES:
        raise ValueError(f"invalid category: {category!r}")
    if confidence not in ALLOWED_CONFIDENCE:
        raise ValueError(f"invalid confidence: {confidence!r}")
    if not isinstance(draft_reply, str) or not (1 <= len(draft_reply) <= 1000):
        raise ValueError("invalid draft_reply")
    if not isinstance(escalate, bool):
        raise ValueError("invalid escalate")

    return {
        "category": category,
        "draft_reply": draft_reply,
        "confidence": confidence,
        "escalate": escalate,
        "error": None,
    }


def _mock_classify(text: str) -> dict:
    """
    Простая эвристика без обращения к платному API — удобно для
    локальной разработки/тестов и для демо, если ключа ещё нет.
    Включается через MOCK_LLM=true в .env.
    """
    lowered = text.lower()
    if any(w in lowered for w in ["оплат", "счет", "счёт", "возврат", "деньги", "чек"]):
        category, confidence = "billing", "medium"
    elif any(w in lowered for w in ["жалоб", "недовол", "плохо", "ужас", "хамств"]):
        category, confidence = "complaint", "medium"
    elif any(w in lowered for w in ["вход", "личный кабинет", "сертификат",
                                     "удостоверение", "доступ", "пароль", "тест"]):
        category, confidence = "support", "medium"
    else:
        category, confidence = "other", "low"

    escalate = confidence == "low"
    draft_reply = (
        "Здравствуйте! Мы получили ваше обращение и уточняем детали, "
        "ответим по существу в ближайшее время."
    )
    return {
        "category": category,
        "draft_reply": draft_reply,
        "confidence": confidence,
        "escalate": escalate,
        "error": None,
    }


def classify_and_draft(text: str) -> dict:
    """
    Главная функция. Возвращает dict с полями:
    category, draft_reply, confidence, escalate, error (None если без ошибки).
    Никогда не выбрасывает исключение наружу — при любой проблеме
    отдаёт fallback-результат.
    """
    mock_mode = os.getenv("MOCK_LLM", "false").lower() == "true"
    api_key = os.getenv("OPENAI_API_KEY")

    if mock_mode or not api_key:
        return _mock_classify(text)

    try:
        from openai import OpenAI  # импорт внутри try — на случай отсутствия пакета

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.2,  # низкая температура — меньше "фантазии"
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            timeout=15,
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        return _validate_and_normalize(data)

    except Exception as exc:  # noqa: BLE001 — это и есть сценарий "если всё сломалось"
        return _fallback_result(str(exc))
