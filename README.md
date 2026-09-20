# AI Triage Service — сервис первичной обработки обращений
### (для системы повышения квалификации педагогических работников)

Сервис принимает текст обращения слушателя курсов ДПО, классифицирует его
(`billing / support / complaint / other`), готовит черновик ответа,
пишет всё в SQLite-журнал и умеет "падать красиво" — при сбое LLM
эскалирует обращение оператору вместо выдуманного ответа.

## 1. Архитектура (5 блоков)

```
Клиент (Postman / curl / фронтенд)
        │  POST /triage {text, channel, client_id}
        ▼
 FastAPI (main.py)
   ├─ валидация входа (Pydantic + проверка channel)
   ├─ rate_limiter.py — лимит N запросов/мин на client_id
   ├─ llm_client.py — системный промпт, temperature=0.2,
   │      строгий JSON-формат, fallback при любой ошибке
   └─ db.py — запись в SQLite (таблица tickets, аудит)
        ▼
 Ответ клиенту {category, draft_reply, confidence, escalate}
```

## 2. Установка и локальный запуск

```bash
git clone <ваш-репозиторий>
cd triage-service

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# откройте .env и при необходимости впишите OPENAI_API_KEY
```

По умолчанию в `.env.example` стоит `MOCK_LLM=true` — сервис работает
на встроенной эвристике без реального обращения к OpenAI (это удобно
для разработки/демо и не требует денег). Когда будете готовы —
поставьте `MOCK_LLM=false` и впишите настоящий `OPENAI_API_KEY`.

Запуск:

```bash
uvicorn main:app --reload --port 8000
```

Swagger-документация: http://127.0.0.1:8000/docs

## 3. Проверка через curl / Postman

```bash
curl -X POST http://127.0.0.1:8000/triage \
  -H "Content-Type: application/json" \
  -d '{
        "text": "Оплатила курс, но статус в кабинете все еще \"не оплачено\"",
        "channel": "email",
        "client_id": "c001"
      }'
```

Ожидаемый ответ:

```json
{
  "category": "billing",
  "draft_reply": "...",
  "confidence": "medium",
  "escalate": false
}
```

В Postman: создайте POST-запрос на `http://127.0.0.1:8000/triage`,
Body → raw → JSON, вставьте тот же payload.

## 4. Контракт API

**POST /triage**

Вход:
| поле | тип | ограничения |
|---|---|---|
| text | string | 1–2000 символов, обязательно |
| channel | string | одно из: `email`, `form`, `chat` |
| client_id | string | обязательно, используется для лимитирования |

Выход:
| поле | тип | значения |
|---|---|---|
| category | string | `billing`, `support`, `complaint`, `other` |
| draft_reply | string | 1–6 предложений |
| confidence | string | `high`, `medium`, `low` |
| escalate | bool | true — передать оператору |

Ошибки: `422` — невалидный вход, `429` — превышен лимит запросов.

## 5. Надёжность и безопасность

- **Валидация**: длина `text`, обязательность полей, допустимые `channel` —
  проверяются Pydantic-моделью и вручную в `main.py`.
- **Секреты**: `OPENAI_API_KEY` читается только из переменных окружения
  (`.env`, не коммитится — см. `.gitignore`).
- **Лимитирование**: `rate_limiter.py` — простое скользящее окно 60 сек,
  не больше `RATE_LIMIT_PER_MINUTE` запросов на один `client_id`.
- **Сценарий "если всё сломалось"**: если LLM недоступна, вернула
  невалидный JSON или произошла любая другая ошибка — `llm_client.py`
  перехватывает исключение и отдаёт `escalate=true` + шаблонный
  `draft_reply` ("передано оператору"). Причина ошибки при этом
  пишется в поле `error` таблицы `tickets` — только для аудита,
  наружу клиенту не отдаётся.

## 6. Журнал (аудит) — SQLite

Файл `tickets.db` создаётся автоматически при первом запуске.
Таблица `tickets`: `id, created_at, client_id, channel, text, category,
confidence, escalate, draft_reply, error`.

Посмотреть журнал:

```bash
python3 -c "from db import fetch_all_tickets; import json; print(json.dumps(fetch_all_tickets(20), ensure_ascii=False, indent=2))"
```

## 7. Прогон 60 тестовых обращений (лог для отчёта)

В файле `sample_tickets.json` — 60 обращений, стилизованных под
реальные вопросы слушателей курсов повышения квалификации педагогов
(оплата, доступ в личный кабинет, сертификаты, жалобы на качество и т.д.).

```bash
# в одном терминале:
uvicorn main:app --port 8000

# в другом терминале:
python3 run_sample_log.py
```

Результат сохранится в `log_60.csv` (текст обращения + ответ сервиса +
HTTP-статус) — это и есть лог из 60 откликов для отчёта/защиты.

## 8. Развёртывание

### Путь A — бесплатный хостинг (например, Render / Railway / Fly.io)

Общая идея (шаги отличаются в деталях в зависимости от площадки):

1. Запушьте репозиторий на GitHub.
2. Создайте новый Web Service на выбранной площадке, подключите репозиторий.
3. Build command: `pip install -r requirements.txt`.
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
5. В настройках Environment добавьте переменные из `.env.example`
   (`OPENAI_API_KEY`, `MOCK_LLM`, `RATE_LIMIT_PER_MINUTE`).
6. После деплоя проверьте публичный URL тем же curl/Postman-запросом,
   что в разделе 3, заменив `127.0.0.1:8000` на публичный адрес.

**Сервис развёрнут и доступен по адресу:**
- Swagger-документация: http://109.172.38.106:8010/docs
- Эндпоинт: http://109.172.38.106:8010/triage

Также можно задеплоить как Docker-контейнер — `Dockerfile` уже готов:

```bash
docker build -t triage-service .
docker run -p 8000:8000 --env-file .env triage-service
```

### Путь B — локальная демонстрация (если хостинг недоступен)

1. Запустите сервис локально (раздел 2–3).
2. Прогоните `run_sample_log.py`, чтобы получить `log_60.csv` и
   заполненную `tickets.db`.
3. Запишите демо-видео (2–3 минуты): показать запрос в Postman →
   ответ сервиса → содержимое `tickets.db` (например, через
   DB Browser for SQLite или простой Python-скрипт).
4. Приложите скриншоты запроса/ответа и содержимого БД к отчёту.

## 9. Что улучшить в v2

- RAG / база знаний по типовым вопросам слушателей курсов.
- Мониторинг (метрики: доля escalate, среднее время ответа).
- Админ-панель для просмотра и разметки журнала.
- Персистентный (не in-memory) rate limiter — Redis, для нескольких воркеров.
