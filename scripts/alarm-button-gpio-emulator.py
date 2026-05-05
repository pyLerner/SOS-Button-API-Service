#!/usr/bin/env python3
"""Локальный эмулятор GPIO-кнопки для разработки без физического устройства.

Скрипт обновляет файл со значением GPIO (`0` или `1`), который затем читает
основной сервис через параметр `[GPIO].value_path` в `alarm-button.toml`.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import os
import time


def write_level(path: Path, level: int) -> None:
    """Записывает уровень 0/1 через временный файл и os.replace — без окна «пустого» value."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(f"{level}\n", encoding="utf-8")
    os.replace(tmp, path)


def run_emulator_loop(value_path: Path, pressed: int, unpressed: int, hold_ms: int, interval_ms: int) -> int:
    """Запускает бесконечный цикл генерации состояний pressed/unpressed."""
    hold_sec = max(hold_ms, 0) / 1000.0
    interval_sec = max(interval_ms, 1) / 1000.0

    # Исходно кнопка отпущена.
    write_level(value_path, unpressed)
    print(f"Эмулятор запущен: value_path={value_path} pressed={pressed} unpressed={unpressed}")
    print("Нажмите Ctrl+C для остановки.")

    try:
        while True:
            write_level(value_path, pressed)
            print("Эмулятор: pressed")
            time.sleep(hold_sec)
            write_level(value_path, unpressed)
            print("Эмулятор: unpressed")
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        write_level(value_path, unpressed)
        print("\nЭмулятор остановлен.")
        return 0


def main() -> int:
    """Точка входа CLI эмулятора."""
    parser = argparse.ArgumentParser(description="Эмулятор GPIO кнопки alarm-button")
    parser.add_argument("--value-path", required=True, help="Путь к файлу уровня GPIO")
    parser.add_argument("--pressed", type=int, default=1, choices=[0, 1], help="Уровень состояния pressed")
    parser.add_argument("--unpressed", type=int, default=0, choices=[0, 1], help="Уровень состояния unpressed")
    parser.add_argument("--hold-ms", type=int, default=400, help="Длительность удержания нажатия в мс")
    parser.add_argument("--interval-ms", type=int, default=1200, help="Период генерации нажатий в мс")
    args = parser.parse_args()
    return run_emulator_loop(
        value_path=Path(args.value_path),
        pressed=args.pressed,
        unpressed=args.unpressed,
        hold_ms=args.hold_ms,
        interval_ms=args.interval_ms,
    )


if __name__ == "__main__":
    raise SystemExit(main())
