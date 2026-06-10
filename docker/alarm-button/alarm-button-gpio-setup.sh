#!/usr/bin/env bash
# Настройка GPIO для Alarm Button на хосте (RK3588 / D-3588).
# Идемпотентен: повторный запуск безопасен.
# Запуск с root (systemd oneshot или вручную).
#
# GPIO_NUM — из /opt/alarm-button/etc/alarm-button-gpio.env или окружения.
# Контейнер alarm-button-api (uid 1000) читает sysfs после export на хосте.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GPIO_ENV="${SCRIPT_DIR}/etc/alarm-button-gpio.env"
CONTAINER_UID=1000
CONTAINER_GID=1000
INSTALL_UNIT=1

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: alarm-button-gpio-setup.sh [--no-install-unit]

  --no-install-unit   Не копировать/включать systemd-юнит (для вызова из unit).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-install-unit)
      INSTALL_UNIT=0
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      die "неизвестный параметр: $1"
      ;;
  esac
done

if [[ -f "$GPIO_ENV" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$GPIO_ENV"
  set +a
fi

N="${GPIO_NUM:-116}"
GPIO_BASE="/sys/class/gpio"
GPIO_PATH="${GPIO_BASE}/gpio${N}"
VALUE_PATH="${GPIO_PATH}/value"

write() {
  local path=$1 val=$2
  if [[ $(id -u) -eq 0 ]]; then
    printf '%s\n' "$val" >"$path"
  else
    printf '%s\n' "$val" | sudo tee "$path" >/dev/null
  fi
}

set_value_permissions() {
  # sysfs value: chown для uid контейнера; если ядро не даёт — chmod o+r.
  if chown "${CONTAINER_UID}:${CONTAINER_GID}" "$VALUE_PATH" 2>/dev/null; then
    chmod u+r "$VALUE_PATH" 2>/dev/null || true
    return 0
  fi
  chmod o+r "$VALUE_PATH" 2>/dev/null || die "не удалось выставить права на ${VALUE_PATH}"
}

install_systemd_unit() {
  local unit_src="${SCRIPT_DIR}/alarm-button-gpio.service"
  local unit_dst="/etc/systemd/system/alarm-button-gpio.service"
  [[ -f "$unit_src" ]] || die "не найден unit: ${unit_src}"
  if [[ $(id -u) -ne 0 ]]; then
    die "для установки unit нужен root"
  fi
  cp "$unit_src" "$unit_dst"
  systemctl daemon-reload
  systemctl enable alarm-button-gpio.service
}

if [[ ! -d "$GPIO_PATH" ]]; then
  write "${GPIO_BASE}/export" "$N"
fi

write "${GPIO_PATH}/direction" "in"
write "${GPIO_PATH}/edge" "both"
set_value_permissions

if (( INSTALL_UNIT )); then
  install_systemd_unit
fi

tr -d '\n' <"$VALUE_PATH"
echo
