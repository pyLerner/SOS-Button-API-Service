#!/usr/bin/env python3
"""Единый раннер Alarm Button.

Поддерживает два режима:
- запуск основного API-сервиса;
- запуск локального GPIO-эмулятора.

Все параметры запуска читаются из TOML-конфига.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import os
import sys
import tomllib


def load_toml(path: Path) -> dict:
    """Загружает TOML-файл и возвращает словарь."""
    with path.open("rb") as fh:
        return tomllib.load(fh)


def run_api(config_path: Path, config: dict) -> int:
    """Запускает uvicorn в этом процессе — Ctrl+C закрывает сервер через shutdown uvicorn и lifespan.

    Раньше использовался вложенный subprocess (uv run uvicorn), из‑за чего SIGINT
    обрабатывался в нескольких процессах и давал «грязный» вывод и гонки при остановке.
    """
    import uvicorn

    api = config.get("api-server", {})
    host = str(api.get("api-host", "0.0.0.0"))
    port = int(api.get("api-port", 8000))
    os.environ["ALARM_BUTTON_CONFIG"] = str(config_path)

    try:
        uvicorn.run(
            "app.main:app",
            host=host,
            port=port,
        )
    except KeyboardInterrupt:
        pass
    return 0


def run_emulator(config_path: Path, config: dict) -> int:
    """Запускает GPIO-эмулятор, используя параметры из [GPIO]/[emulator]."""
    gpio = config.get("GPIO", {})
    emulator = config.get("emulator", {})

    value_path_raw = gpio.get("value_path")
    if not value_path_raw:
        print("Ошибка: в [GPIO] не задан value_path для эмулятора.", file=sys.stderr)
        print(f"Конфиг: {config_path}", file=sys.stderr)
        return 2

    from importlib.util import spec_from_file_location, module_from_spec  # локальный импорт для простоты

    emulator_script = Path(__file__).parent / "scripts" / "alarm-button-gpio-emulator.py"
    spec = spec_from_file_location("alarm_button_gpio_emulator", emulator_script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load emulator module: {emulator_script}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    return module.run_emulator_loop(
        value_path=Path(str(value_path_raw)),
        pressed=int(gpio.get("pressed", 1)),
        unpressed=int(gpio.get("unpressed", 0)),
        hold_ms=int(emulator.get("hold_ms", 400)),
        interval_ms=int(emulator.get("interval_ms", 1200)),
    )


def main() -> int:
    """Парсит аргументы CLI и запускает нужный режим."""
    parser = argparse.ArgumentParser(description="Runner для Alarm Button API/Emulator")
    parser.add_argument(
        "mode",
        choices=["api", "emulator"],
        nargs="?",
        default="api",
        help="Режим запуска: api (по умолчанию) или emulator",
    )
    parser.add_argument(
        "--config",
        default="alarm-button.toml",
        help="Путь к конфигу TOML (по умолчанию ./alarm-button.toml)",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_toml(config_path)

    if args.mode == "api":
        return run_api(config_path, config)
    return run_emulator(config_path, config)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        sys.exit(0)
