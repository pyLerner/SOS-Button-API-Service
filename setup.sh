#!/bin/bash
# Одноразовая настройка GPIO для Alarm Button (D-3588 J38 K8 -> Linux GPIO 155).
# Скрипт идемпотентен: повторный запуск безопасен.
# Предполагается запуск с root-правами (обычно через systemd oneshot-юнит).

set -euo pipefail

N="${GPIO_NUM:-116}"
GPIO_BASE="/sys/class/gpio"
GPIO_PATH="${GPIO_BASE}/gpio${N}"

write() {
  # Унифицированная запись в sysfs: напрямую под root или через sudo в shell-сессии пользователя.
  local path=$1 val=$2
  if [[ $(id -u) -eq 0 ]]; then
    printf '%s\n' "$val" >"$path"
  else
    printf '%s\n' "$val" | sudo tee "$path" >/dev/null
  fi
}

if [[ ! -d "$GPIO_PATH" ]]; then
  # Экспорт GPIO только если он еще не экспортирован в sysfs.
  write "${GPIO_BASE}/export" "$N"
fi

# Направление входа и уведомления по обоим фронтам нужны для чтения состояния кнопки.
write "${GPIO_PATH}/direction" "in"
write "${GPIO_PATH}/edge" "both"

# Текущий уровень (0/1) печатаем в stdout для лога systemd после запуска юнита.
tr -d '\n' <"${GPIO_PATH}/value"
echo
