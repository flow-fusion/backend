# Production Deployment Guide

Полное руководство по развёртыванию FlowFusion.

## Быстрый старт (Local Development)

```bash
# Скопировать конфигурацию
cp .env.example .env

# Запустить все сервисы
docker-compose up -d

# Проверить статус
docker-compose ps

# Health check
curl http://localhost:8000/health
```

## Production развёртывание

### 1. Подготовка сервера

```bash
# Установить Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Установить Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. Настройка окружения

```bash
cp .env.production .env
nano .env  # Отредактировать значения
```

**Обязательные переменные:**
```bash
DATABASE_URL=postgresql://postgres:password@localhost:5432/flowfusion
GITLAB_WEBHOOK_SECRET=random_32_chars_minimum
GITLAB_API_TOKEN=glpat-xxxxxxxxxxxx
```

### 3. Запуск production

```bash
# Собрать и запустить
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d

# Проверить статус
docker-compose -f docker-compose.prod.yml ps
```

### 4. Настройка HTTPS (опционально)

```nginx
# /etc/nginx/sites-available/flowfusion
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# Включить и получить HTTPS сертификат
sudo ln -s /etc/nginx/sites-available/flowfusion /etc/nginx/sites-enabled/
sudo nginx -t
sudo certbot --nginx -d your-domain.com
```

## Настройка GitLab

1. Settings → Webhooks
2. URL: `https://your-domain.com/webhooks/gitlab`
3. Secret Token: значение из `GITLAB_WEBHOOK_SECRET`
4. Trigger: Push events, Merge request events
5. Test → Push events

## Настройка Jira

1. Получить API token: https://id.atlassian.com/manage-profile/security/api-tokens
2. Добавить в `.env`:
   ```bash
   JIRA_URL=https://your-company.atlassian.net
   JIRA_EMAIL=your-email@company.com
   JIRA_TOKEN=your_api_token
   JIRA_AUTO_POST=true
   ```
3. Перезапустить worker: `docker-compose restart worker`

## Мониторинг

```bash
# Health checks
curl http://localhost:8000/health
curl http://localhost:8000/ready

# Логи
docker-compose logs -f api
docker-compose logs -f worker

# Статистика очередей
docker-compose exec redis redis-cli LLEN event_queue
```

## Масштабирование

### Горизонтальное (worker)
```bash
docker-compose -f docker-compose.prod.yml up -d --scale worker=4
```

### Вертикальное
Изменить в `docker-compose.prod.yml`:
```yaml
services:
  worker:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 1G
```

## Backup

```bash
# PostgreSQL backup
docker-compose exec postgres pg_dump -U postgres flowfusion > backup.sql

# Восстановление
cat backup.sql | docker-compose exec -T postgres psql -U postgres flowfusion
```

## Security Checklist

- [ ] GITLAB_WEBHOOK_SECRET установлен (32+ символа)
- [ ] DATABASE_PASSWORD изменён с default
- [ ] HTTPS настроен
- [ ] Debug mode выключен
- [ ] Firewall настроен (только 80, 443, 22)
