# API-ALARM-BUTTON

HTTP интерфейс сервиса доступен по адресу:

`http://<host>:<port>`

Значения берутся из секции `[api-server]` файла `alarm-button.toml`.

## Соглашения

- Формат запросов/ответов: JSON, UTF-8
- Для JSON-запросов: `Content-Type: application/json`
- Ключи JSON: по возможности kebab-case; исключение: поле `source` от `/api/ping` (строковый идентификатор из конфига)
- Версионный префикс API: `/api/alarm-button/v1/`
- Endpoint `ping` остается вне versioned префикса: `/api/ping`

## 1) Проверка доступности

### `GET /api/ping`

Ответ `200 OK`:

```json
{
  "running": "OK",
  "timestamp-utc": "2026-03-29T12:34:56.789+00:00",
  "source": "gpio-alarm-button"
}
```

Поля:
- `running` (`string`) - всегда `"OK"` при успешной работе
- `timestamp-utc` (`string`) - текущее UTC время в ISO 8601
- `source` (`string`) - значение из `[api-server] source-string` в `alarm-button.toml`, идентификатор развёртывания/источника

## 2) Поток событий кнопки (SSE)

### `GET /api/alarm-button/v1/button/events`

Открывает долгоживущее SSE соединение (`text/event-stream`).

Рекомендуемые заголовки клиента:
- `Accept: text/event-stream`
- `Cache-Control: no-cache`

Поведение:
- Соединение удерживается сервером (keep-alive комментарии отправляются периодически).
- Если `alarm.initial_state=true`, сразу после подключения отправляется текущее состояние кнопки.
- Если `alarm.initial_state=false`, initial event не отправляется.
- Далее события идут только при изменениях состояния с учетом фильтров `[alarm]`.

Формат события:

```text
event: alarm-button-state
data: {"button-state":"pressed","source":"gpio-alarm-button","timestamp-utc":"2026-03-29T12:34:56.789+00:00"}
```

Поля `data`:
- `button-state` (`string`) - `pressed` или `unpressed`
- `source` (`string`) - всегда значение `[api-server] source-string` из `alarm-button.toml` (как в `GET /api/ping`)
- `timestamp-utc` (`string`) - время формирования в UTC (ISO 8601)

## Ошибки

- `500 Internal Server Error` - внутренняя ошибка сервера
- `503 Service Unavailable` - может использоваться при недоступности GPIO (по решению интеграции)

## Источник состояния и фильтры

Состояние определяется из `[GPIO]`:
- `pressed = 1|0`
- `unpressed = 0|1`

Обработка нажатий в `[alarm]`:
- `debounce_ms` - фильтрация дребезга
- `min_press_ms` - минимальная длительность удержания для сигнала `pressed`
- `repress_timeout_sec` - блок повторного `pressed` на заданный интервал

## Локальная эмуляция GPIO

Для разработки без физического GPIO можно использовать `GPIO.value_path` в `alarm-button.toml`.

Пример:

```toml
[GPIO]
pin_number = 116
pressed = 1
unpressed = 0
value_path = "./var/alarm-button-gpio-value"
```

Запуск эмулятора:

```bash
uv run --python 3.13 python scripts/alarm-button-gpio-emulator.py \
  --value-path ./var/alarm-button-gpio-value \
  --pressed 1 --unpressed 0
```

