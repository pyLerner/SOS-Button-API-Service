#!/bin/sh
set -eu

GPIO_NUM="${GPIO_NUM:-116}"
GPIO_WAIT_SECONDS="${GPIO_WAIT_SECONDS:-60}"
GPIO_POLL_INTERVAL="${GPIO_POLL_INTERVAL:-0.5}"
VALUE_PATH="/sys/class/gpio/gpio${GPIO_NUM}/value"

log() {
  printf '%s %s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$*"
}

wait_for_gpio() {
  deadline=$(( $(date +%s) + GPIO_WAIT_SECONDS ))
  while :; do
    if [ -r "$VALUE_PATH" ]; then
      if value=$(cat "$VALUE_PATH" 2>/dev/null); then
        case "$value" in
          0|1)
            log "GPIO ${GPIO_NUM} ready (value=${value}), starting app"
            return 0
            ;;
        esac
      fi
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      log "ERROR: timeout waiting for ${VALUE_PATH}"
      log "ERROR: run alarm-button-gpio-setup.sh or systemctl start alarm-button-gpio.service on host"
      exit 1
    fi
    log "waiting for host GPIO setup: ${VALUE_PATH}"
    sleep "$GPIO_POLL_INTERVAL"
  done
}

wait_for_gpio
exec "$@"
