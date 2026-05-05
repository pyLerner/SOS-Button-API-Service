"""Внутренний асинхронный SSE-broker для fan-out событий кнопки."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ButtonEvent:
    """DTO события состояния кнопки."""

    button_state: str
    source: str
    timestamp_utc: str

    def to_json(self) -> str:
        """Сериализует событие в JSON с kebab-case ключами."""
        return json.dumps(
            {
                "button-state": self.button_state,
                "source": self.source,
                "timestamp-utc": self.timestamp_utc,
            },
            ensure_ascii=True,
        )


class SseBroker:
    """Простейший pub/sub для доставки событий всем активным SSE-клиентам."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[ButtonEvent]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[ButtonEvent]:
        """Регистрирует клиента и возвращает его персональную очередь событий."""
        queue: asyncio.Queue[ButtonEvent] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(queue)
            LOGGER.info("SSE клиент подключен, total=%s", len(self._subscribers))
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[ButtonEvent]) -> None:
        """Удаляет клиента из подписчиков и освобождает его очередь."""
        async with self._lock:
            self._subscribers.discard(queue)
            LOGGER.info("SSE клиент отключен, total=%s", len(self._subscribers))

    async def publish(self, event: ButtonEvent) -> None:
        """Рассылает событие всем подписчикам, отбрасывая самый старый элемент при переполнении."""
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            if queue.full():
                _ = queue.get_nowait()
            queue.put_nowait(event)

