#!/bin/sh
set -eu

GPIO_NUM="${GPIO_NUM:-116}"
GPIO_POLL_INTERVAL_MIN="${GPIO_POLL_INTERVAL_MIN:-1}"
GPIO_POLL_INTERVAL_MAX="${GPIO_POLL_INTERVAL_MAX:-60}"
GPIO_LOG_EVERY="${GPIO_LOG_EVERY:-30}"
VALUE_PATH="/sys/class/gpio/gpio${GPIO_NUM}/value"

log() {
  printf '%s %s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$*"
}

gpio_ready() {
  if [ ! -r "$VALUE_PATH" ]; then
    return 1
  fi
  value=$(cat "$VALUE_PATH" 2>/dev/null) || return 1
  case "$value" in
    0|1) return 0 ;;
    *) return 1 ;;
  esac
}

wait_for_gpio() {
  interval="$GPIO_POLL_INTERVAL_MIN"
  last_log=0

  while :; do
    if gpio_ready; then
      value=$(cat "$VALUE_PATH")
      log "GPIO ${GPIO_NUM} ready (value=${value}), starting app"
      return 0
    fi

    now=$(date +%s)
    if [ "$last_log" -eq 0 ] || [ $((now - last_log)) -ge "$GPIO_LOG_EVERY" ]; then
      log "waiting for host GPIO setup: ${VALUE_PATH} (next check in ${interval}s)"
      last_log=$now
    fi

    sleep "$interval"
    if [ "$interval" -lt "$GPIO_POLL_INTERVAL_MAX" ]; then
      interval=$((interval * 2))
      if [ "$interval" -gt "$GPIO_POLL_INTERVAL_MAX" ]; then
        interval="$GPIO_POLL_INTERVAL_MAX"
      fi
    fi
  done
}

wait_for_gpio
exec "$@"
