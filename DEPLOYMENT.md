# FlowFusion Production Deployment Guide

Полное руководство по развёртыванию FlowFusion в production.

## 📋 Оглавление

1. [Требования](#требования)
2. [Быстрый старт (Local Development)](#быстрый-старт-local-development)
3. [Production Deployment](#production-deployment)
4. [Настройка GitLab](#настройка-gitlab)
5. [Настройка Jira](#настройка-jira)
6. [Мониторинг и логирование](#мониторинг-и-логирование)
7. [Масштабирование](#масштабирование)
8. [Troubleshooting](#troubleshooting)

---

## Требования

### Минимальные (до 1000 событий/день):
- **CPU:** 2 cores
- **RAM:** 2 GB
- **Storage:** 10 GB SSD
- **Services:** PostgreSQL, Redis

### Рекомендуемые (до 10000 событий/день):
- **CPU:** 4 cores
- **RAM:** 4 GB
- **Storage:** 20 GB SSD
- **Services:** PostgreSQL, Redis

### Для высоких нагрузок (10000+ событий/день):
- **CPU:** 8+ cores
- **RAM:** 8+ GB
- **Storage:** 50+ GB SSD
- **Services:** PostgreSQL (репликация), Redis Cluster

---

## Быстрый старт (Local Development)

### 1. Клонирование и настройка

```bash
cd /Users/dmitriy/Documents/ai_concurs_backend

# Скопировать переменные окружения
cp .env.example .env

# Отредактировать .env (минимум для локальной разработки)
# GITLAB_WEBHOOK_SECRET=dev_secret_for_testing
```

### 2. Запуск через Docker Compose

```bash
# Запустить все сервисы
docker-compose up -d

# Проверить статус
docker-compose ps

# Посмотреть логи
docker-compose logs -f api
docker-compose logs -f worker
```

### 3. Проверка работы

```bash
# Health check
curl http://localhost:8000/health

# Readiness check
curl http://localhost:8000/ready

# Swagger UI (только в debug режиме)
open http://localhost:8000/docs
```

### 4. Тестовый webhook

```bash
curl -X POST http://localhost:8000/webhooks/gitlab \
  -H "Content-Type: application/json" \
  -H "X-Gitlab-Event: Push Hook" \
  -H "X-Gitlab-Token: dev_secret_for_testing" \
  -d '{
    "object_kind": "push",
    "ref": "refs/heads/feature/TEST-123-test",
    "project": {"name": "test-repo"},
    "commits": [{
      "id": "abc123",
      "message": "Test commit",
      "author": {"name": "Test"}
    }]
  }'
```

---

## Production Deployment

### 1. Подготовка сервера

```bash
# Обновить систему
sudo apt update && sudo apt upgrade -y

# Установить Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Установить Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Добавить пользователя в группу docker
sudo usermod -aG docker $USER
```

### 2. Настройка окружения

```bash
# Скопировать production конфиг
cp .env.production .env

# Отредактировать .env с реальными значениями
nano .env

# Сгенерировать безопасный секрет для webhook
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Запуск production

```bash
# Собрать образы
docker-compose -f docker-compose.prod.yml build

# Запустить сервисы
docker-compose -f docker-compose.prod.yml up -d

# Проверить статус
docker-compose -f docker-compose.prod.yml ps

# Посмотреть логи
docker-compose -f docker-compose.prod.yml logs -f
```

### 4. Настройка Nginx (опционально, для HTTPS)

```nginx
# /etc/nginx/sites-available/flowfusion
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Включить и перезагрузить
sudo ln -s /etc/nginx/sites-available/flowfusion /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 5. Настройка HTTPS (Let's Encrypt)

```bash
# Установить Certbot
sudo apt install certbot python3-certbot-nginx -y

# Получить сертификат
sudo certbot --nginx -d your-domain.com

# Автообновление сертификата
sudo certbot renew --dry-run
```

---

## Настройка GitLab

### 1. Создать Personal Access Token

1. Зайти в GitLab → Settings → Access Tokens
2. Создать токен со scopes:
   - `read_api`
   - `read_repository`
3. Скопировать токен в `.env`:
   ```
   GITLAB_API_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
   ```

### 2. Настроить Webhook в GitLab

1. Зайти в проект GitLab → Settings → Webhooks
2. Заполнить:
   - **URL:** `https://your-domain.com/webhooks/gitlab`
   - **Secret Token:** (из `.env` GITLAB_WEBHOOK_SECRET)
   - **Trigger:**
     - ✅ Push events
     - ✅ Merge request events
   - ✅ Enable SSL verification (если HTTPS)
3. Нажать **Test** → **Push events**

### 3. Проверка webhook

```bash
# Посмотреть логи API
docker-compose -f docker-compose.prod.yml logs -f api | grep webhook

# Должно быть:
# Successfully processed Push Hook for repo/branch
```

---

## Настройка Jira

### 1. Создать API Token

1. Зайти: https://id.atlassian.com/manage-profile/security/api-tokens
2. Create API token
3. Скопировать токен

### 2. Настроить доступы

Пользователь с API токеном должен иметь права:
- **Browse Projects** — для чтения задач
- **Add Comments** — для постинга саммари
- **Transition Issues** — для смены статусов

### 3. Обновить .env

```bash
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_TOKEN=your_api_token
JIRA_AUTO_POST=true
```

### 4. Перезапустить worker

```bash
docker-compose -f docker-compose.prod.yml restart worker
```

---

## Мониторинг и логирование

### Health Checks

```bash
# Basic health
curl https://your-domain.com/health

# Readiness с проверкой БД и Redis
curl https://your-domain.com/ready
```

### Логи

```bash
# API логи
docker-compose -f docker-compose.prod.yml logs -f api

# Worker логи
docker-compose -f docker-compose.prod.yml logs -f worker

# Поиск ошибок
docker-compose -f docker-compose.prod.yml logs | grep ERROR
```

### Статистика очередей

```python
# Подключиться к worker контейнеру
docker-compose -f docker-compose.prod.yml exec worker python3

# Проверить очередь
from app.processing.event_queue_service import EventQueueService
queue = EventQueueService()
print(queue.get_queue_stats())
```

### Prometheus Metrics (опционально)

Добавить в `docker-compose.prod.yml`:

```yaml
services:
  exporter:
    image: oliver006/redis_exporter
    ports:
      - "9121:9121"
    command: -redis.addr redis:6379
```

---

## Масштабирование

### Горизонтальное масштабирование Worker

```bash
# Увеличить количество worker'ов
docker-compose -f docker-compose.prod.yml up -d --scale worker=4
```

### Вертикальное масштабирование

Изменить в `docker-compose.prod.yml`:

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 2G
  
  worker:
    deploy:
      replicas: 4
      resources:
        limits:
          cpus: '2'
          memory: 1G
```

### Репликация PostgreSQL

Для высоких нагрузок использовать managed решения:
- AWS RDS
- Google Cloud SQL
- Azure Database for PostgreSQL

---

## Troubleshooting

### Webhook не приходит

```bash
# Проверить логи
docker-compose logs api | grep "POST /webhooks"

# Проверить токен
docker-compose logs api | grep "Invalid token"

# Проверить GitLab webhook delivery
GitLab → Settings → Webhooks → Recent Deliveries
```

### Worker не обрабатывает события

```bash
# Проверить подключение к Redis
docker-compose exec worker redis-cli -h redis ping

# Проверить очередь
docker-compose exec redis redis-cli LLEN event_queue

# Перезапустить worker
docker-compose restart worker
```

### Ошибки подключения к БД

```bash
# Проверить БД
docker-compose exec postgres pg_isready

# Проверить логи БД
docker-compose logs postgres

# Проверить connection string
docker-compose exec api python -c "from app.shared.config import get_settings; print(get_settings().DATABASE_URL)"
```

### Jira не постит комментарии

```bash
# Проверить логи
docker-compose logs worker | grep "Jira"

# Проверить подключение
docker-compose exec worker python3 -c "
from app.jira_integration.jira_client import JiraClient
from app.jira_integration.config import JiraConfig
config = JiraConfig.from_env()
client = JiraClient(config)
print(client.get_issue('TEST-1'))
"
```

---

## Backup и восстановление

### Backup PostgreSQL

```bash
# Создать дамп
docker-compose exec postgres pg_dump -U postgres flowfusion > backup.sql

# Восстановить
cat backup.sql | docker-compose exec -T postgres psql -U postgres flowfusion
```

### Backup Redis

```bash
# Создать snapshot
docker-compose exec redis redis-cli SAVE

# Скопировать файл
docker cp flowfusion-redis:/data/dump.rdb ./redis-backup.rdb
```

---

## Security Checklist

- [ ] GITLAB_WEBHOOK_SECRET установлен и безопасен (32+ символа)
- [ ] GITLAB_API_TOKEN имеет минимальные необходимые права
- [ ] JIRA_TOKEN имеет минимальные необходимые права
- [ ] DATABASE_PASSWORD изменён с default
- [ ] REDIS_PASSWORD установлен
- [ ] HTTPS настроен (Let's Encrypt)
- [ ] Debug mode выключен (`DEBUG=false`)
- [ ] Swagger UI отключен в production
- [ ] CORS настроен для конкретных доменов
- [ ] Firewall настроен (только 80, 443, 22)

---

## Поддержка

При возникновении проблем:

1. Проверить логи: `docker-compose logs -f`
2. Проверить health endpoints: `/health`, `/ready`
3. Проверить GitLab webhook delivery
4. Проверить подключение к БД и Redis

**133 теста проходят** ✅
