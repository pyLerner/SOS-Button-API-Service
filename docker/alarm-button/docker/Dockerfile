FROM python:3.13-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml /app/

RUN python - <<'PY'
import pathlib
import tomllib

data = tomllib.loads(pathlib.Path("/app/pyproject.toml").read_text(encoding="utf-8"))
deps = data.get("project", {}).get("dependencies", [])
pathlib.Path("/app/requirements.txt").write_text("\n".join(deps) + "\n", encoding="utf-8")
PY

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install -r /app/requirements.txt

COPY app /app/app
COPY alarm-button-run.py /app/

FROM python:3.13-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ALARM_BUTTON_CONFIG=/app/etc/alarm-button.toml

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        tzdata \
    && ln -sf /usr/share/zoneinfo/Etc/UTC /etc/localtime \
    && echo "Etc/UTC" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/* \
    && rm -rf /usr/share/doc/* /usr/share/man/* /usr/share/info/*

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/requirements.txt /app/requirements.txt
COPY --from=builder /app/app /app/app
COPY --from=builder /app/alarm-button-run.py /app/
COPY docker/alarm-button/docker/entry-point.sh /app/entry-point.sh

RUN chmod +x /app/entry-point.sh \
    && useradd --uid 1000 --create-home --shell /usr/sbin/nologin alarmbutton \
    && chown -R alarmbutton:alarmbutton /app /opt/venv

USER alarmbutton

EXPOSE 7130

ENTRYPOINT ["/app/entry-point.sh"]
CMD ["python", "alarm-button-run.py", "api", "--config", "/app/etc/alarm-button.toml"]
