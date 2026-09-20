"""
run_sample_log.py — прогоняет 60 тестовых обращений (sample_tickets.json)
через запущенный сервис (POST /triage) и сохраняет результат в log_60.csv.

Использование:
    1. Запустить сервис в одном терминале:
         uvicorn main:app --reload --port 8000
    2. В другом терминале выполнить:
         python run_sample_log.py

По умолчанию скрипт слегка "растягивает" запросы по времени, чтобы не
упереться в лимитирование (RATE_LIMIT_PER_MINUTE), если оно маленькое.
"""
import csv
import json
import time
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8000"
TICKETS_FILE = Path(__file__).parent / "sample_tickets.json"
OUTPUT_FILE = Path(__file__).parent / "log_60.csv"
DELAY_SECONDS = 0.3  # пауза между запросами, чтобы не словить 429


def main():
    tickets = json.loads(TICKETS_FILE.read_text(encoding="utf-8"))

    rows = []
    for i, ticket in enumerate(tickets, start=1):
        try:
            resp = requests.post(f"{BASE_URL}/triage", json=ticket, timeout=20)
            status = resp.status_code
            body = resp.json()
        except Exception as exc:  # сервис недоступен и т.п.
            status = "ERR"
            body = {"category": "", "draft_reply": str(exc),
                    "confidence": "", "escalate": ""}

        row = {
            "n": i,
            "client_id": ticket["client_id"],
            "channel": ticket["channel"],
            "text": ticket["text"],
            "http_status": status,
            "category": body.get("category", ""),
            "confidence": body.get("confidence", ""),
            "escalate": body.get("escalate", ""),
            "draft_reply": body.get("draft_reply", ""),
        }
        rows.append(row)
        print(f"[{i}/{len(tickets)}] {ticket['client_id']} -> "
              f"{row['category']} / {row['confidence']} / escalate={row['escalate']}")
        time.sleep(DELAY_SECONDS)

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nГотово! Лог из {len(rows)} обращений сохранён в {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
