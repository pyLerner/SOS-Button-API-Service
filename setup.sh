#!/bin/bash
# Одноразовая настройка GPIO для SOS (D-3588 J38 K8 → Linux GPIO 155).
# Идемпотентно: повторный запуск не падает. Требует root (systemd oneshot).

set -euo pipefail

N="${GPIO_NUM:-116}"
GPIO_BASE="/sys/class/gpio"
GPIO_PATH="${GPIO_BASE}/gpio${N}"

write() {
  local path=$1 val=$2
  if [[ $(id -u) -eq 0 ]]; then
    printf '%s\n' "$val" >"$path"
  else
    printf '%s\n' "$val" | sudo tee "$path" >/dev/null
  fi
}

if [[ ! -d "$GPIO_PATH" ]]; then
  write "${GPIO_BASE}/export" "$N"
fi

write "${GPIO_PATH}/direction" "in"
write "${GPIO_PATH}/edge" "both"

# Текущий уровень (0/1) — для лога после старта юнита
tr -d '\n' <"${GPIO_PATH}/value"
echo
