"""
rate_limiter.py — простое лимитирование "N запросов в минуту на client_id".

Реализация примитивная (in-memory, скользящее окно 60 секунд).
Для одного процесса и учебного/демо-масштаба этого достаточно.
Если понадобится несколько воркеров или продакшн — заменить на Redis.
"""
import time
from collections import defaultdict, deque

_requests_by_client: dict[str, deque] = defaultdict(deque)


def is_allowed(client_id: str, limit_per_minute: int) -> bool:
    now = time.time()
    window_start = now - 60
    q = _requests_by_client[client_id]

    # убираем метки времени старше 60 секунд
    while q and q[0] < window_start:
        q.popleft()

    if len(q) >= limit_per_minute:
        return False

    q.append(now)
    return True
