#!/usr/bin/env bash
# Развёртывание из каталога, где лежат подкаталог alarm-button/ и архив alarm-button*.tar.gz
# — загрузка образа (docker load), остановка/удаление контейнера при обновлении, запуск compose.
# Опционально: копирование alarm-button → /opt/alarm-button (как в docker-compose volumes).
set -euo pipefail

COMPOSE_REL_PATH="${COMPOSE_REL_PATH:-docker/docker-compose.yml}"
DEFAULT_CONTAINER_NAME="${CONTAINER_NAME:-alarm-button-api}"
OPT_TARGET="/opt/alarm-button"

usage() {
  cat <<'EOF'
Usage: install-docker-from-tar.sh [options] [DEPLOY_DIR]

  DEPLOY_DIR — каталог с alarm-button/ и alarm-button*.tar.gz (по умолчанию: текущий).

Options:
  --copy-to-opt     Скопировать alarm-button в /opt/alarm-button (нужен root).
  --no-up           Только docker load (и опционально --copy-to-opt), без compose up.
  --setup-gpio      После --copy-to-opt: установить unit и запустить GPIO setup на хосте.
  --tar FILE        Явный путь к .tar.gz; иначе ищется alarm-button*.tar.gz в DEPLOY_DIR.
  -h, --help        Справка.

Переменные окружения:
  TAR_FILE          То же, что --tar.
  CONTAINER_NAME    Имя контейнера для остановки перед обновлением (по умолчанию: alarm-button-api).
  COMPOSE_REL_PATH  Путь к compose от корня bundle (по умолчанию: docker/docker-compose.yml).

Несколько файлов alarm-button*.tar.gz: берётся самый новый по дате модификации.
EOF
}

log() { printf '%s\n' "$*"; }

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "команда не найдена: $1"
}

pick_newest_tar() {
  local -n __arr=$1
  local newest="" mt=-1 t
  [[ ${#__arr[@]} -gt 0 ]] || return 1
  for f in "${__arr[@]}"; do
    if [[ ! -f "$f" ]]; then
      continue
    fi
    t=$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null || echo 0)
    if (( t > mt )); then
      mt=$t
      newest=$f
    fi
  done
  [[ -n "$newest" ]] || return 1
  printf '%s' "$newest"
}

resolve_tar_path() {
  local dir="$1"
  if [[ -n "${TAR_FILE:-}" ]]; then
    [[ -f "$TAR_FILE" ]] || die "файл не найден: $TAR_FILE"
    realpath -s "$TAR_FILE" 2>/dev/null || readlink -f "$TAR_FILE" 2>/dev/null || printf '%s' "$TAR_FILE"
    return
  fi
  local -a candidates=()
  shopt -s nullglob
  candidates=( "${dir}"/alarm-button*.tar.gz )
  shopt -u nullglob
  ((${#candidates[@]} == 0)) && die "в $dir нет файлов alarm-button*.tar.gz (задайте --tar или TAR_FILE=)"
  if ((${#candidates[@]} > 1)); then
    log "Найдено несколько архивов, выбран самый новый по mtime:"
    printf '  %s\n' "${candidates[@]}"
  fi
  pick_newest_tar candidates || die "не удалось выбрать архив"
}

stop_existing_container() {
  local name="$1"
  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -Fxq "$name"; then
    log "Останавливаю и удаляю контейнер «$name» (обновление образа)…"
    docker rm -f "$name" >/dev/null
  fi
}

compose_down_project() {
  local root="$1"
  local cf="${root}/${COMPOSE_REL_PATH}"
  [[ -f "$cf" ]] || return 0
  log "docker compose down в ${root}…"
  ( cd "$root" && docker compose -f "$COMPOSE_REL_PATH" down --remove-orphans 2>/dev/null ) || true
}

copy_project_to_opt() {
  local src="$1"
  [[ -d "$src" ]] || die "нет каталога: $src"
  need_cmd rsync
  log "Копирование ${src} → ${OPT_TARGET} …"
  mkdir -p "${OPT_TARGET}"
  rsync -a --delete "${src}/" "${OPT_TARGET}/"
  mkdir -p "${OPT_TARGET}/logs"
  chown -R 1000:1000 "${OPT_TARGET}/logs"
  chmod +x "${OPT_TARGET}/alarm-button-gpio-setup.sh" 2>/dev/null || true
}

setup_gpio_on_host() {
  local setup="${OPT_TARGET}/alarm-button-gpio-setup.sh"
  [[ -x "$setup" ]] || chmod +x "$setup"
  log "Настройка GPIO на хосте (${setup})…"
  "$setup"
  systemctl enable --now alarm-button-gpio.service
}

main() {
  local deploy_dir=""
  local copy_to_opt=0
  local no_up=0
  local setup_gpio=0
  local tar_explicit=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h | --help)
        usage
        exit 0
        ;;
      --copy-to-opt)
        copy_to_opt=1
        shift
        ;;
      --no-up)
        no_up=1
        shift
        ;;
      --setup-gpio)
        setup_gpio=1
        shift
        ;;
      --tar)
        [[ -n "${2:-}" ]] || die "ожидается путь после --tar"
        tar_explicit=$2
        shift 2
        ;;
      -*)
        die "неизвестный параметр: $1"
        ;;
      *)
        [[ -z "$deploy_dir" ]] || die "указано несколько каталогов"
        deploy_dir=$1
        shift
        ;;
    esac
  done

  need_cmd docker
  deploy_dir="${deploy_dir:-.}"
  deploy_dir=$(cd "$deploy_dir" && pwd)

  if [[ -n "$tar_explicit" ]]; then
    TAR_FILE=$tar_explicit
  fi

  local src_project="${deploy_dir}/alarm-button"
  [[ -d "$src_project" ]] || die "ожидается каталог: ${src_project}"

  local tar_path
  tar_path=$(resolve_tar_path "$deploy_dir")
  [[ -f "$tar_path" ]] || die "архив образа: $tar_path"

  local project_root="$src_project"
  if (( copy_to_opt )); then
    if [[ "${EUID}" -ne 0 ]]; then
      die "для --copy-to-opt запустите от root: sudo $0 ..."
    fi
    copy_project_to_opt "$src_project"
    project_root="${OPT_TARGET}"
    if (( setup_gpio )); then
      setup_gpio_on_host
    else
      log "Подсказка: для GPIO на хосте выполните:"
      log "  sudo ${OPT_TARGET}/alarm-button-gpio-setup.sh"
      log "  sudo systemctl enable --now alarm-button-gpio.service"
      log "или переустановите с флагом --setup-gpio"
    fi
  fi

  local compose_file="${project_root}/${COMPOSE_REL_PATH}"
  [[ -f "$compose_file" ]] || die "не найден compose: $compose_file (COMPOSE_REL_PATH=${COMPOSE_REL_PATH})"

  compose_down_project "$project_root"
  stop_existing_container "$DEFAULT_CONTAINER_NAME"

  log "Загрузка образа из ${tar_path} …"
  gunzip -c "$tar_path" | docker load

  if (( no_up )); then
    log "Готово (--no-up: контейнер не запускался)."
    exit 0
  fi

  log "Запуск stack в ${project_root} …"
  ( cd "$project_root" && docker compose -f "$COMPOSE_REL_PATH" up -d --no-build )
  log "Готово."
}

main "$@"
