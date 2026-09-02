# Автозапуск Compose на Ubuntu

`compose.yml` задаёт `restart: unless-stopped` для контейнеров. Unit systemd дополнительно запускает сам Compose-стек после загрузки Docker и сети. Это нужно для восстановления после перезагрузки testdev-сервера.

## Установка на testdev

Предполагается, что проект находится в `/home/alex/ai-process-architect`. Если путь другой, измените `WorkingDirectory` и повторите копирование unit-файла.

```bash
sudo install -m 0644 infra/systemd/ai-process-architect.service \
  /etc/systemd/system/ai-process-architect.service
sudo systemctl daemon-reload
sudo systemctl enable ai-process-architect.service
sudo systemctl start ai-process-architect.service
```

Проверка:

```bash
systemctl is-enabled ai-process-architect.service
systemctl is-active ai-process-architect.service
systemctl status ai-process-architect.service --no-pager
docker compose --env-file .env.compose ps
```

## Профиль мониторинга

Обычный стек запускается без дополнительных сервисов. Чтобы вместе с приложением поднимались Prometheus, Grafana и PostgreSQL exporter, добавьте в `/etc/systemd/system/ai-process-architect.service.d/monitoring.conf`:

```ini
[Service]
Environment=COMPOSE_PROFILES=monitoring
```

Затем выполните:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ai-process-architect.service
```

При выключении unit использует `docker compose stop`, поэтому данные PostgreSQL, Prometheus и Grafana остаются в named volumes.

## Проверка восстановления

```bash
sudo systemctl reboot
```

После повторного входа:

```bash
systemctl is-active ai-process-architect.service
docker compose --env-file .env.compose ps
curl -fsS http://127.0.0.1:5173/ >/dev/null
curl -fsS http://127.0.0.1:5173/health
```

Если Docker установлен из snap и бинарник находится не в `/usr/bin/docker`, замените путь в `ExecStart` и `ExecStop` на результат `command -v docker`.
