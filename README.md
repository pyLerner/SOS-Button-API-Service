# Alarm-Button-API-Service

FastAPI сервис для мониторинга кнопки тревоги и отправки событий клиентам через SSE.

## Требования

- Linux (для реального GPIO используется sysfs путь `/sys/class/gpio`)
- Python 3.13
- `uv` для управления окружением и зависимостями
- Права на чтение GPIO `value` и выполнение `setup.sh` (обычно root/systemd)

## Структура проекта

- `app/main.py` - FastAPI endpoints, SSE-поток, lifecycle приложения
- `app/config.py` - загрузка TOML-конфига и строгая валидация параметров
- `app/services/gpio_monitor.py` - мониторинг GPIO с фильтрами `[alarm]`
- `app/services/sse_broker.py` - асинхронный pub/sub для SSE клиентов
- `scripts/alarm-button-gpio-emulator.py` - локальный эмулятор GPIO без железа
- `deploy/systemd/` - юниты и env-шаблон для прод-запуска
- `setup.sh` - oneshot подготовка GPIO в sysfs

## Конфигурация

Основной файл: `alarm-button.toml`.

```toml
[GPIO]
pin_number = 116
pressed = 1
unpressed = 0
# value_path = "./var/alarm-button-gpio-value"

[alarm]
initial_state = true
debounce_ms = 50
min_press_ms = 150
repress_timeout_sec = 2

[api-server]
api-host = "0.0.0.0"
api-port = 8000

[log]
log_dir = "./logs"
log_name = "alarm-button.log"
max_log_files = 5
max_log_size = "10M"
loglevel = "info"
```

Пояснения:
- `GPIO.pressed/unpressed` задают соответствие электрического уровня 0/1 и логического состояния.
- `GPIO.value_path` (опционально) включает режим локального эмулятора.
- `alarm.initial_state=true` отправляет текущее состояние сразу после SSE-подключения.
- `debounce_ms` фильтрует дребезг контакта.
- `min_press_ms` отсекает слишком короткие нажатия.
- `repress_timeout_sec` блокирует повторную генерацию `pressed` в заданный интервал.
- `loglevel` поддерживает `info` и `debug`: при `info` в лог попадают только стабильное нажатие/отжатие, сформированный сигнал и итог фильтрации; при `debug` — также все промежуточные шаги монитора GPIO (дребезг, таймер удержания по тикам и т.п.).

## Локальный запуск (uv + Python 3.13)

```bash
uv python install 3.13
uv venv --python 3.13
source .venv/bin/activate
uv sync
```

Запуск API (параметры берутся из `alarm-button.toml`):

```bash
uv run --python 3.13 python ./alarm-button-run.py api --config ./alarm-button.toml
```

## Локальный эмулятор GPIO

1) В `alarm-button.toml` включить `GPIO.value_path`, например:

```toml
[GPIO]
value_path = "./var/alarm-button-gpio-value"
```

2) Запустить эмулятор (все параметры берутся из конфига: `[GPIO]` и `[emulator]`):

```bash
uv run --python 3.13 python ./alarm-button-run.py emulator --config ./alarm-button.toml
```

Эмулятор циклически пишет `pressed -> unpressed`, а API читает это как обычный GPIO.

CLI раннера:

- `python ./alarm-button-run.py api --config path-to-conf`
- `python ./alarm-button-run.py emulator --config path-to-conf`
- если `--config` не задан, используется `./alarm-button.toml`

## API

- `GET /api/ping`
- `GET /api/alarm-button/v1/button/events` (SSE)

Подробный контракт: `API-ALARM-BUTTON.md`.

## Установка systemd

1. Скопировать проект в `/opt/alarm-button-api-service`.
2. Скопировать конфиг в `/etc/alarm-button/alarm-button.toml`.
3. Скопировать env:
   - `deploy/systemd/alarm-button.env` -> `/etc/default/alarm-button`
4. Скопировать юниты:
   - `deploy/systemd/alarm-button-gpio-setup.service` -> `/etc/systemd/system/`
   - `deploy/systemd/alarm-button-api.service` -> `/etc/systemd/system/`
5. Применить:

```bash
sudo systemctl daemon-reload
sudo systemctl enable alarm-button-gpio-setup.service alarm-button-api.service
sudo systemctl start alarm-button-api.service
```

Проверка:

```bash
sudo systemctl status alarm-button-gpio-setup.service
sudo systemctl status alarm-button-api.service
```

## Smoke-check

1) Проверка доступности:

```bash
curl -s http://127.0.0.1:8000/api/ping
```

2) Проверка SSE:

```bash
curl -N http://127.0.0.1:8000/api/alarm-button/v1/button/events
```

3) Проверка фильтров:
- короткое нажатие (< `min_press_ms`) фильтруется;
- повторное нажатие в окне `repress_timeout_sec` фильтруется;
- результат каждого нажатия виден в логе `logs/alarm-button.log`.
