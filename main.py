"""
main.py — сервис первичной обработки обращений слушателей курсов
повышения квалификации педагогических работников.

Запуск локально:
    uvicorn main:app --reload --port 8000

Документация (Swagger UI) появится на:
    http://127.0.0.1:8000/docs
"""
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from db import init_db, insert_ticket
from llm_client import classify_and_draft
from rate_limiter import is_allowed

load_dotenv()

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "5"))
ALLOWED_CHANNELS = {"email", "form", "chat"}

app = FastAPI(title="AI Triage Service — ДПО педагогов")


@app.on_event("startup")
def on_startup():
    init_db()


class TriageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    channel: str
    client_id: str = Field(..., min_length=1, max_length=200)


class TriageResponse(BaseModel):
    category: str
    draft_reply: str
    confidence: str
    escalate: bool


@app.post("/triage", response_model=TriageResponse)
def triage(payload: TriageRequest):
    # 1. Валидация входа (доп. к тому, что уже делает Pydantic)
    if payload.channel not in ALLOWED_CHANNELS:
        raise HTTPException(
            status_code=422,
            detail=f"channel must be one of {sorted(ALLOWED_CHANNELS)}",
        )

    # 2. Лимитирование на client_id
    if not is_allowed(payload.client_id, RATE_LIMIT_PER_MINUTE):
        raise HTTPException(
            status_code=429,
            detail="Too many requests, try again in a minute",
        )

    # 3. Обработка LLM (внутри уже есть fallback на любые ошибки)
    result = classify_and_draft(payload.text)

    # 4. Запись в БД (аудит) — пишем всегда, даже если была ошибка
    insert_ticket(
        client_id=payload.client_id,
        channel=payload.channel,
        text=payload.text,
        category=result["category"],
        confidence=result["confidence"],
        escalate=result["escalate"],
        draft_reply=result["draft_reply"],
        error=result.get("error"),
    )

    # 5. Ответ клиенту (без поля error — оно только для аудита в БД)
    return TriageResponse(
        category=result["category"],
        draft_reply=result["draft_reply"],
        confidence=result["confidence"],
        escalate=result["escalate"],
    )


@app.get("/health")
def health():
    return {"status": "ok"}
