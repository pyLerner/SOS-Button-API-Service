"""Точка входа FastAPI для Alarm Button API Service."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import AppConfig, load_config
from app.logging_setup import setup_logging
from app.services.gpio_monitor import GpioMonitor
from app.services.sse_broker import ButtonEvent, SseBroker


LOGGER = logging.getLogger(__name__)


def _sse_line(event: str | None = None, data: str | None = None, comment: str | None = None) -> str:
    """Формирует одну SSE-посылку из `event/data` или keepalive-комментария."""
    lines: list[str] = []
    if comment is not None:
        lines.append(f": {comment}")
    if event is not None:
        lines.append(f"event: {event}")
    if data is not None:
        lines.append(f"data: {data}")
    return "\n".join(lines) + "\n\n"


def _utc_now_iso() -> str:
    """Возвращает UTC время в ISO-8601 с миллисекундами."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def create_app() -> FastAPI:
    """Создает и настраивает экземпляр FastAPI-приложения."""
    cfg_path = os.getenv("ALARM_BUTTON_CONFIG", "alarm-button.toml")
    config = load_config(cfg_path)
    setup_logging(config.log)
    broker = SseBroker()
    monitor = GpioMonitor(config.gpio, config.alarm, broker, event_source=config.api_server.source_string)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """Управляет жизненным циклом фонового монитора GPIO."""
        await monitor.start()
        LOGGER.info("Сервис запущен, config=%s", cfg_path)
        try:
            yield
        finally:
            await monitor.stop()
            LOGGER.info("Сервис остановлен")

    app = FastAPI(title="Alarm Button API Service", lifespan=lifespan)
    app.state.config = config
    app.state.broker = broker
    app.state.monitor = monitor

    @app.get("/api/ping")
    async def ping() -> JSONResponse:
        """Health-check endpoint для проверки доступности сервиса."""
        cfg: AppConfig = app.state.config
        return JSONResponse(
            {
                "running": "OK",
                "timestamp-utc": _utc_now_iso(),
                "source": cfg.api_server.source_string,
            }
        )

    @app.get("/api/alarm-button/v1/button/events")
    async def button_events(request: Request) -> StreamingResponse:
        """Открывает SSE-поток событий состояния кнопки."""
        app_config: AppConfig = request.app.state.config
        app_broker: SseBroker = request.app.state.broker
        app_monitor: GpioMonitor = request.app.state.monitor
        queue = await app_broker.subscribe()

        async def event_stream():
            """Генерирует SSE-сообщения до отключения клиента."""
            try:
                if app_config.alarm.initial_state:
                    initial = app_monitor.get_current_state()
                    if initial is not None:
                        event = ButtonEvent(
                            button_state=initial,
                            source=app_config.api_server.source_string,
                            timestamp_utc=_utc_now_iso(),
                        )
                        yield _sse_line(event="alarm-button-state", data=event.to_json())
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                        yield _sse_line(event="alarm-button-state", data=event.to_json())
                    except asyncio.TimeoutError:
                        # Регулярный keepalive нужен, чтобы прокси не закрывали idle-соединение.
                        yield _sse_line(comment="keepalive")
            finally:
                await app_broker.unsubscribe(queue)

        headers = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
        return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)

    return app


app = create_app()

