"""Модуль загрузки и валидации конфигурации Alarm Button API Service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import tomllib


SIZE_RE = re.compile(r"^(?P<num>\d+)(?P<unit>[KMG]?)$", re.IGNORECASE)


@dataclass(slots=True, frozen=True)
class GpioConfig:
    """Параметры GPIO и источник чтения уровня контакта.

    `value_path` поддерживает локальный эмулятор: если путь задан, сервис
    читает значение 0/1 из этого файла вместо системного sysfs пути.
    """

    pin_number: int
    pressed: int
    unpressed: int
    value_path: Path | None


@dataclass(slots=True, frozen=True)
class AlarmConfig:
    """Параметры фильтрации нажатий и поведения SSE initial event."""

    initial_state: bool
    debounce_ms: int
    min_press_ms: int
    repress_timeout_sec: int


@dataclass(slots=True, frozen=True)
class ApiServerConfig:
    """Параметры bind-адреса API; source_string попадает в JSON /api/ping как ключ source."""

    host: str
    port: int
    source_string: str


@dataclass(slots=True, frozen=True)
class LogConfig:
    """Параметры файлового логирования и ротации."""

    log_dir: Path
    log_name: str
    max_log_files: int
    max_log_size: int
    loglevel: str


@dataclass(slots=True, frozen=True)
class AppConfig:
    """Корневой объект конфигурации приложения."""

    gpio: GpioConfig
    alarm: AlarmConfig
    api_server: ApiServerConfig
    log: LogConfig


def _require(section: dict, key: str, section_name: str):
    """Возвращает обязательный ключ из секции, иначе возбуждает ValueError."""
    if key not in section:
        raise ValueError(f"Missing '{key}' in [{section_name}]")
    return section[key]


def _parse_size(size_value: str) -> int:
    """Преобразует размер вида 10M/512K в байты."""
    match = SIZE_RE.match(size_value.strip())
    if not match:
        raise ValueError("Invalid max_log_size format, expected like 10M")
    number = int(match.group("num"))
    unit = match.group("unit").upper()
    multiplier = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3}[unit]
    return number * multiplier


def _load_toml(path: Path) -> dict:
    """Загружает TOML-файл конфигурации."""
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_config(config_path: str | None = None) -> AppConfig:
    """Загружает и валидирует полную конфигурацию приложения."""
    path_str = config_path or os.getenv("ALARM_BUTTON_CONFIG", "alarm-button.toml")
    path = Path(path_str)
    data = _load_toml(path)

    gpio_data = _require(data, "GPIO", "root")
    alarm_data = _require(data, "alarm", "root")
    api_data = _require(data, "api-server", "root")
    log_data = _require(data, "log", "root")

    raw_value_path = gpio_data.get("value_path")
    gpio = GpioConfig(
        pin_number=int(_require(gpio_data, "pin_number", "GPIO")),
        pressed=int(_require(gpio_data, "pressed", "GPIO")),
        unpressed=int(_require(gpio_data, "unpressed", "GPIO")),
        value_path=Path(str(raw_value_path)) if raw_value_path else None,
    )
    if gpio.pressed not in (0, 1) or gpio.unpressed not in (0, 1):
        raise ValueError("GPIO pressed/unpressed must be 0 or 1")
    if gpio.pressed == gpio.unpressed:
        raise ValueError("GPIO pressed and unpressed cannot be equal")

    alarm = AlarmConfig(
        initial_state=bool(_require(alarm_data, "initial_state", "alarm")),
        debounce_ms=int(_require(alarm_data, "debounce_ms", "alarm")),
        min_press_ms=int(_require(alarm_data, "min_press_ms", "alarm")),
        repress_timeout_sec=int(_require(alarm_data, "repress_timeout_sec", "alarm")),
    )
    if alarm.debounce_ms < 0 or alarm.min_press_ms < 0 or alarm.repress_timeout_sec < 0:
        raise ValueError("Alarm timing values must be >= 0")

    api_server = ApiServerConfig(
        host=str(_require(api_data, "api-host", "api-server")),
        port=int(_require(api_data, "api-port", "api-server")),
        source_string=str(_require(api_data, "source-string", "api-server")),
    )

    loglevel = str(_require(log_data, "loglevel", "log")).lower()
    if loglevel not in ("info", "debug"):
        raise ValueError("loglevel must be info or debug")

    log = LogConfig(
        log_dir=Path(str(_require(log_data, "log_dir", "log"))),
        log_name=str(_require(log_data, "log_name", "log")),
        max_log_files=int(_require(log_data, "max_log_files", "log")),
        max_log_size=_parse_size(str(_require(log_data, "max_log_size", "log"))),
        loglevel=loglevel,
    )
    return AppConfig(gpio=gpio, alarm=alarm, api_server=api_server, log=log)

