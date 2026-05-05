# Alarm-Button-API-Service

FastAPI сервис для мониторинга кнопки тревоги и отправки событий клиентам через SSE.

## Требования

- Linux (для реального GPIO используется sysfs `/sys/class/gpio`)
- Python 3.13
- Утилита `uv` в `PATH` (и при **локальной** разработке, и при **systemd**: `ExecStart` вызывает `uv run`)

## Структура проекта

- `app/main.py` - FastAPI endpoints, SSE-поток, lifecycle приложения
- `app/config.py` - загрузка TOML-конфига и строгая валидация параметров
- `app/services/gpio_monitor.py` - мониторинг GPIO с фильтрами `[alarm]`
- `app/services/sse_broker.py` - асинхронный pub/sub для SSE клиентов
- `scripts/alarm-button-gpio-emulator.py` - локальный эмулятор GPIO без железа
- `alarm-button-run.py` - единая точка входа для режимов `api` и `emulator` (читает TOML)
- `deploy/systemd/` - юниты и пример переменных окружения для запуска под systemd
- `setup.sh` - разовый экспорт пина GPIO, направление `in`, маска ребёр `both` (запускается из юнита `alarm-button-gpio-setup.service`; номер берётся из `GPIO_NUM` в `/etc/default/alarm-button`)

## Конфигурация

Единственный формат конфига — TOML. Путь задаётся так:

| Сценарий | Файл |
|----------|------|
| Локально, `./alarm-button-run.py` | `./alarm-button.toml` по умолчанию или явный `--config путь` |
| Локально, при прямом `uvicorn` | переменная окружения `ALARM_BUTTON_CONFIG` должна указывать на тот же TOML |
| Установка через `alarm-button.sh install` | копируется как `/etc/alarm-button/alarm-button.toml`; сервис читает его по `CONFIG_PATH` в `/etc/default/alarm-button` |

Пример (см. также репозиторный `alarm-button.toml`):

```toml
[GPIO]
pin_number = 116
pressed = 1
unpressed = 0
# value_path = "./var/alarm-button-gpio-value"   # если задан — чтение из файла (эмулятор), а не из sysfs

[alarm]
initial_state = true
debounce_ms = 50
min_press_ms = 150
repress_timeout_sec = 2

[emulator]
hold_ms = 400
interval_ms = 1200

[api-server]
api-host = "0.0.0.0"
api-port = 8000
source-string = "gpio-alarm-button"

[log]
log_dir = "./logs"
log_name = "alarm-button.log"
max_log_files = 5
max_log_size = "10M"
loglevel = "info"
```

Пояснения:

- `api-server.source-string` — поле `"source"` в `GET /api/ping` и в JSON поля `data` каждого SSE-события с типом `alarm-button-state`.
- `GPIO.pressed` / `GPIO.unpressed` — соответствие уровня 0/1 логическим `pressed` / `unpressed`.
- `GPIO.value_path` (опционально) — режим чтения уровня из файла (пара в паре с процессом `emulator`); для «железа» не задавайте или закомментируйте, чтобы использовался `/sys/class/gpio/gpio<N>/value` по `pin_number`.
- `alarm.initial_state=true` — сразу после подключения к SSE отправляется текущее состояние кнопки.
- `debounce_ms`, `min_press_ms`, `repress_timeout_sec` — дребезг, минимальная длительность нажатия, интервал блокировки повторного `pressed`.
- `[emulator]` — только для `alarm-button-run.py emulator`; API из этого раздела не читает.
- `loglevel`: `info` — стабильные нажатия/отпускания, сформированный сигнал, итог фильтров; `debug` — дополнительно шаги цикла монитора.

**Продакшен (systemd):** адрес привязки процесса задаёт **`API_HOST`** и **`API_PORT`** в [`/etc/default/alarm-button`](deploy/systemd/alarm-button.env) — их удобно держать согласованными с `[api-server] api-host` и `api-port` в том же TOML. Одноразовый `setup.sh` использует переменную **`GPIO_NUM`** из того же файла — её нужно выставить **в тот же номер**, что и `GPIO.pin_number` в конфиге, пока включён режим sysfs (без `value_path`).

## Локальная установка окружения и запуск

```bash
uv python install 3.13
uv venv --python 3.13
source .venv/bin/activate   # или полагаться на uv run без активации
uv sync
```

Запуск API (хост и порт берутся из `[api-server]` в выбранном TOML):

```bash
uv run --python 3.13 python ./alarm-button-run.py api --config ./alarm-button.toml
```

Эквивалент через Makefile (`CONFIG` по умолчанию `./alarm-button.toml`):

```bash
make sync
make run
make emulator    # второй терминал, если нужен цикл записи в value_path
```

Для связки «эмулятор + API»:

1. В TOML задайте `GPIO.value_path` (файл должен быть доступен на чтение/запись; каталог заранее создайте при необходимости).
2. В одном терминале: `make emulator` (или `uv run ... alarm-button-run.py emulator --config ...`).
3. В другом: `make run`.

Без `value_path` сервис читает sysfs; у пользователя процесса должны быть права на чтение `.../gpio<N>/value` (часто сервис под `root`).

## Установка и запуск под systemd

### Автоматическая установка (рекомендуется)

Из корня репозитория, от root:

```bash
sudo ./alarm-button.sh install
```

Скрипт:

- копирует код и lock-файлы в **`/usr/local/alarm-button`** (рабочий каталог `WORKDIR`);
- копирует текущий репозиторный `alarm-button.toml` в **`/etc/alarm-button/alarm-button.toml`**;
- формирует **`/etc/default/alarm-button`** из шаблона `deploy/systemd/alarm-button.env` с подстановкой `WORKDIR`;
- ставит юниты `alarm-button-gpio-setup.service` и `alarm-button-api.service`, выполняет `daemon-reload`, `enable` и `restart` API.

**После первой установки** в каталоге установки нужно один раз подтянуть зависимости (скрипт этого не делает):

```bash
sudo sh -c 'cd /usr/local/alarm-button && uv sync'
```

Проверка и просмотр логов:

```bash
sudo systemctl status alarm-button-gpio-setup.service
sudo systemctl status alarm-button-api.service
sudo journalctl -u alarm-button-api.service -f
```

Удаление:

```bash
sudo ./alarm-button.sh uninstall [--dry-run]
```

### Ручная установка (альтернатива)

Если не используете `alarm-button.sh`: скопируйте проект в выбранный каталог, положите TOML в `/etc/alarm-button/alarm-button.toml`, создайте `/etc/default/alarm-button` по образцу `deploy/systemd/alarm-button.env` (пути `WORKDIR`, `CONFIG_PATH`, `GPIO_NUM`, `API_HOST`, `API_PORT`), установите юниты из `deploy/systemd/` в `/etc/systemd/system/`, затем `daemon-reload`, `enable` и `start`. Выполните `uv sync` в `WORKDIR` до первого `start`.

## API

- `GET /api/ping`
- `GET /api/alarm-button/v1/button/events` (SSE, тип события `alarm-button-state`)

Подробный контракт: [`API-ALARM-BUTTON.md`](API-ALARM-BUTTON.md).

## Smoke-check

Подставьте хост и порт из вашего TOML (ниже пример для `127.0.0.1:8000`). Команда `make smoke` подставляет `api-host` / `api-port` из того же файла, что и `CONFIG` по умолчанию (`$(CONFIG)` в Makefile — обычно `./alarm-button.toml`); для `0.0.0.0` при проверке используется `127.0.0.1`.

```bash
curl -s http://127.0.0.1:8000/api/ping
curl -N http://127.0.0.1:8000/api/alarm-button/v1/button/events
```

Поведение фильтров проверяйте по логу: путь из `log_dir` / `log_name` в конфиге (на проде задайте абсолютный `log_dir` в TOML, если не хотите писать относительно `WORKDIR`).
