#!/usr/bin/env bash
# Установка/удаление Alarm Button API Service.
# Использование:
#   ./alarm-button.sh install [--dry-run]
#   ./alarm-button.sh uninstall [--dry-run]

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_WORKDIR="/usr/local/alarm-button"
DEFAULT_ENV_TARGET="/etc/default/alarm-button"
DEFAULT_CONFIG_DIR="/etc/alarm-button"
DEFAULT_CONFIG_TARGET="${DEFAULT_CONFIG_DIR}/alarm-button.toml"
SYSTEMD_DIR="/etc/systemd/system"

ACTION="${1:-}"
FLAG="${2:-}"
DRY_RUN=0

if [[ -z "${ACTION}" ]]; then
  echo "Ошибка: не указано действие. Используйте install | uninstall [--dry-run]" >&2
  exit 2
fi

if [[ "${FLAG}" == "--dry-run" ]]; then
  DRY_RUN=1
elif [[ -n "${FLAG}" ]]; then
  echo "Ошибка: неизвестный параметр '${FLAG}'. Разрешен только --dry-run" >&2
  exit 2
fi

if [[ "${ACTION}" != "install" && "${ACTION}" != "uninstall" ]]; then
  echo "Ошибка: действие должно быть install или uninstall" >&2
  exit 2
fi

run() {
  if [[ ${DRY_RUN} -eq 1 ]]; then
    echo "[dry-run] $*"
  else
    eval "$@"
  fi
}

require_root() {
  if [[ ${DRY_RUN} -eq 0 && "$(id -u)" -ne 0 ]]; then
    echo "Ошибка: выполните скрипт от root (или через sudo)." >&2
    exit 1
  fi
}

install_service() {
  require_root

  echo "==> Установка Alarm Button в ${DEFAULT_WORKDIR}"

  run "mkdir -p '${DEFAULT_WORKDIR}'"
  run "mkdir -p '${DEFAULT_CONFIG_DIR}'"

  # Копируем основные файлы проекта в рабочий каталог.
  run "cp -r '${ROOT_DIR}/app' '${DEFAULT_WORKDIR}/'"
  run "cp -r '${ROOT_DIR}/scripts' '${DEFAULT_WORKDIR}/'"
  run "cp -r '${ROOT_DIR}/deploy' '${DEFAULT_WORKDIR}/'"
  run "cp '${ROOT_DIR}/setup.sh' '${DEFAULT_WORKDIR}/'"
  run "cp '${ROOT_DIR}/alarm-button.toml' '${DEFAULT_WORKDIR}/'"
  run "cp '${ROOT_DIR}/pyproject.toml' '${DEFAULT_WORKDIR}/'"
  run "cp '${ROOT_DIR}/uv.lock' '${DEFAULT_WORKDIR}/'"
  run "cp '${ROOT_DIR}/.python-version' '${DEFAULT_WORKDIR}/'"

  run "cp '${ROOT_DIR}/alarm-button.toml' '${DEFAULT_CONFIG_TARGET}'"

  # Формируем env-файл с дефолтным WORKDIR=/usr/local/alarm-button.
  if [[ ${DRY_RUN} -eq 1 ]]; then
    echo "[dry-run] write ${DEFAULT_ENV_TARGET} from deploy/systemd/alarm-button.env"
  else
    sed "s|^WORKDIR=.*|WORKDIR=${DEFAULT_WORKDIR}|" \
      "${ROOT_DIR}/deploy/systemd/alarm-button.env" > "${DEFAULT_ENV_TARGET}"
  fi

  run "cp '${ROOT_DIR}/deploy/systemd/alarm-button-gpio-setup.service' '${SYSTEMD_DIR}/'"
  run "cp '${ROOT_DIR}/deploy/systemd/alarm-button-api.service' '${SYSTEMD_DIR}/'"

  run "systemctl daemon-reload"
  run "systemctl enable alarm-button-gpio-setup.service alarm-button-api.service"
  run "systemctl restart alarm-button-api.service"

  echo "==> Установка завершена"
}

uninstall_service() {
  require_root

  echo "==> Удаление Alarm Button"
  run "systemctl stop alarm-button-api.service || true"
  run "systemctl disable alarm-button-api.service alarm-button-gpio-setup.service || true"

  run "rm -f '${SYSTEMD_DIR}/alarm-button-api.service'"
  run "rm -f '${SYSTEMD_DIR}/alarm-button-gpio-setup.service'"
  run "rm -f '${DEFAULT_ENV_TARGET}'"
  run "systemctl daemon-reload"

  # Удаляем каталог установки и конфиг.
  run "rm -rf '${DEFAULT_WORKDIR}'"
  run "rm -f '${DEFAULT_CONFIG_TARGET}'"
  run "rmdir '${DEFAULT_CONFIG_DIR}' 2>/dev/null || true"

  echo "==> Удаление завершено"
}

if [[ "${ACTION}" == "install" ]]; then
  install_service
else
  uninstall_service
fi
