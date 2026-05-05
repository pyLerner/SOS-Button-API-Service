"""Монитор GPIO-кнопки с антидребезгом и защитой от случайных нажатий."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import time

from app.config import AlarmConfig, GpioConfig
from app.services.sse_broker import ButtonEvent, SseBroker


LOGGER = logging.getLogger(__name__)


class GpioMonitor:
    """Фоновый монитор уровня GPIO и генератор бизнес-событий кнопки."""

    def __init__(
        self,
        gpio_cfg: GpioConfig,
        alarm_cfg: AlarmConfig,
        broker: SseBroker,
        *,
        event_source: str,
    ) -> None:
        """Инициализирует монитор и вычисляет путь к источнику GPIO-уровня."""
        self._gpio_cfg = gpio_cfg
        self._alarm_cfg = alarm_cfg
        self._broker = broker
        # Строка SSE/source из [api-server] source-string (как в ping).
        self._event_source = event_source
        # Если задан value_path, используется эмулятор/кастомный источник.
        self._gpio_value_path = gpio_cfg.value_path or Path(f"/sys/class/gpio/gpio{gpio_cfg.pin_number}/value")
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

        # Служебное состояние фильтров.
        self._last_raw_level: int | None = None
        self._last_raw_change_ts = 0.0
        self._stable_state: str | None = None
        self._press_start_ts: float | None = None
        self._last_pressed_emitted_ts = -1e9
        self._last_emitted_state: str | None = None
        self._gpio_missing_logged = False
        # Для одного INFO при отфильтрованной попытке (только при loglevel=info).
        self._emitted_pressed_this_press: bool = False
        self._peak_hold_this_press_sec: float = 0.0

    def get_current_state(self) -> str | None:
        """Возвращает текущее стабильное состояние кнопки."""
        return self._stable_state

    def _read_gpio_level(self) -> int | None:
        """Считывает физический уровень из файла источника; None = кратковременно пусто/невалидно."""
        raw_text = self._gpio_value_path.read_text(encoding="utf-8")
        value = raw_text.strip()
        if value not in ("0", "1"):
            return None
        level = int(value)
        if level not in (0, 1):
            raise ValueError(f"Unexpected GPIO level: {level}")
        return level

    def _level_to_state(self, level: int) -> str:
        """Преобразует уровень GPIO в логическое состояние по конфигу."""
        if level == self._gpio_cfg.pressed:
            return "pressed"
        if level == self._gpio_cfg.unpressed:
            return "unpressed"
        raise ValueError(f"GPIO level {level} does not match pressed/unpressed mapping")

    async def start(self) -> None:
        """Запускает фоновой цикл мониторинга, если он еще не запущен."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Останавливает монитор: сигнал + отмена задачи, чтобы не ждать очередной sleep."""
        self._stop_event.set()
        if self._task is not None:
            t = self._task
            self._task.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _emit(self, state: str) -> None:
        """Публикует итоговое событие кнопки в SSE-брокер (`source` = конфиг api-server.source-string)."""
        now_utc = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        await self._broker.publish(
            ButtonEvent(button_state=state, source=self._event_source, timestamp_utc=now_utc),
        )
        self._last_emitted_state = state
        if state == "pressed":
            self._emitted_pressed_this_press = True
        LOGGER.info("Сигнал сформирован: button-state=%s source=%s", state, self._event_source)

    async def _run(self) -> None:
        """Основной цикл обработки GPIO c применением всех защит из [alarm]."""
        debounce_sec = self._alarm_cfg.debounce_ms / 1000.0
        min_press_sec = self._alarm_cfg.min_press_ms / 1000.0
        repress_timeout_sec = float(self._alarm_cfg.repress_timeout_sec)

        LOGGER.debug("Монитор GPIO запущен, pin=%s, source=%s", self._gpio_cfg.pin_number, self._gpio_value_path)
        try:
            while not self._stop_event.is_set():
                now = time.monotonic()
                try:
                    raw_level = self._read_gpio_level()
                except FileNotFoundError:  # pragma: no cover
                    if not self._gpio_missing_logged:
                        LOGGER.error(
                            "Источник GPIO не найден: %s. Запустите setup.sh/юнит или настройте эмулятор.",
                            self._gpio_value_path,
                        )
                        self._gpio_missing_logged = True
                    else:
                        LOGGER.debug("Источник GPIO по-прежнему недоступен: %s", self._gpio_value_path)
                    await asyncio.sleep(0.2)
                    continue
                except Exception as exc:  # pragma: no cover
                    LOGGER.exception("Ошибка чтения GPIO: %s", exc)
                    await asyncio.sleep(0.2)
                    continue
                else:
                    self._gpio_missing_logged = False

                if raw_level is None:
                    await asyncio.sleep(0.005)
                    continue

                if raw_level != self._last_raw_level:
                    self._last_raw_level = raw_level
                    self._last_raw_change_ts = now
                    LOGGER.debug("Обнаружен физический переход уровня: level=%s", raw_level)

                if now - self._last_raw_change_ts < debounce_sec:
                    await asyncio.sleep(0.02)
                    continue

                current_state = self._level_to_state(raw_level)
                if current_state != self._stable_state:
                    prev_stable = self._stable_state
                    self._stable_state = current_state
                    LOGGER.info("Стабильное состояние кнопки: %s", current_state)

                    if (
                        prev_stable == "pressed"
                        and current_state == "unpressed"
                        and not self._emitted_pressed_this_press
                    ):
                        if self._peak_hold_this_press_sec < min_press_sec:
                            LOGGER.info(
                                "Итог обработки: нажатие отфильтровано (короткое удержание, max %.3fs < %.3fs)",
                                self._peak_hold_this_press_sec,
                                min_press_sec,
                            )
                        else:
                            LOGGER.info(
                                "Итог обработки: нажатие отфильтровано (таймаут повтора)"
                            )

                    if current_state == "pressed":
                        self._press_start_ts = now
                        self._emitted_pressed_this_press = False
                        self._peak_hold_this_press_sec = 0.0
                        LOGGER.debug("Старт таймера удержания нажатия")
                    else:
                        self._press_start_ts = None
                        if self._last_emitted_state == "pressed":
                            await self._emit("unpressed")

                if self._stable_state == "pressed" and self._press_start_ts is not None:
                    hold_sec = now - self._press_start_ts
                    self._peak_hold_this_press_sec = max(self._peak_hold_this_press_sec, hold_sec)
                    if hold_sec < min_press_sec:
                        LOGGER.debug(
                            "Нажатие отфильтровано: короткое удержание %.3fs < %.3fs",
                            hold_sec,
                            min_press_sec,
                        )
                    elif now - self._last_pressed_emitted_ts < repress_timeout_sec:
                        LOGGER.debug(
                            "Нажатие отфильтровано: действует таймаут повтора, осталось %.3fs",
                            repress_timeout_sec - (now - self._last_pressed_emitted_ts),
                        )
                    if hold_sec >= min_press_sec and now - self._last_pressed_emitted_ts >= repress_timeout_sec:
                        if self._last_emitted_state != "pressed":
                            self._last_pressed_emitted_ts = now
                            await self._emit("pressed")

                await asyncio.sleep(0.02)
        except asyncio.CancelledError:
            LOGGER.debug("Монитор GPIO: задача отменена при остановке сервера")
            raise
        finally:
            LOGGER.debug("Монитор GPIO остановлен")

