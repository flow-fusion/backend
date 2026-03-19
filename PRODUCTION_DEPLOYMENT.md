# FlowFusion Production Deployment Guide

Полное руководство по развёртыванию FlowFusion в production.

---

## 📋 Оглавление

1. [Требования](#требования)
2. [Быстрая установка](#быстрая-установка)
3. [Конфигурация](#конфигурация)
4. [Запуск](#запуск)
5. [Мониторинг](#мониторинг)
6. [Масштабирование](#масштабирование)
7. [Troubleshooting](#troubleshooting)

---

## 📦 Требования

### Минимальные (до 1000 событий/день):

| Ресурс | Требование |
|--------|------------|
| **CPU** | 2 cores |
| **RAM** | 4 GB |
| **Storage** | 20 GB SSD |
| **OS** | Linux (Ubuntu 20.04+) |

### Рекомендуемые (до 10000 событий/день):

| Ресурс | Требование |
|--------|------------|
| **CPU** | 4 cores |
| **RAM** | 8 GB |
| **Storage** | 50 GB SSD |
| **OS** | Linux (Ubuntu 22.04+) |

### Для Ollama (локальный AI):

| Модель | RAM | CPU |
|--------|-----|-----|
| **llama3.2** | 4 GB | 2 cores |
| **llama3.1:8b** | 8 GB | 4 cores |
| **mixtral:8x7b** | 32 GB | 8 cores |

---

## 🚀 Быстрая установка

### 1. Установить Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# macOS
brew install --cask docker
```

### 2. Клонировать репозиторий

```bash
git clone <repository-url> flowfusion
cd flowfusion
```

### 3. Настроить окружение

```bash
cp .env.example .env
nano .env  # Отредактировать значения
```

### 4. Запустить

```bash
# Development
docker-compose up -d

# Production
docker-compose -f docker-compose.prod.yml up -d
```

### 5. Проверить

```bash
docker-compose ps
curl http://localhost:8000/health
```

---

## ⚙️ Конфигурация

### Обязательные переменные

```bash
# Database
DB_USER=postgres
DB_PASSWORD=secure_password_here
DB_NAME=flowfusion

# GitLab Webhook
GITLAB_WEBHOOK_SECRET=random_secret_32_chars_minimum
```

### Опциональные переменные

```bash
# GitLab API (для enriched context)
GITLAB_API_TOKEN=glpat-xxxxxxxxxxxx

# AI Configuration
AI_PROVIDER=ollama  # ollama, openai, openrouter, anthropic
AI_MODEL=llama3.2
AI_AUTO_GENERATE=true

# Jira Integration
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=user@company.com
JIRA_TOKEN=jira_api_token
JIRA_AUTO_POST=false
```

---

## 🎯 Запуск в Production

### 1. Подготовить сервер

```bash
# Обновить систему
sudo apt update && sudo apt upgrade -y

# Установить Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Установить Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. Настроить firewall

```bash
# Открыть только необходимые порты
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 443/tcp   # HTTPS (через reverse proxy)
sudo ufw enable
```

### 3. Настроить Nginx (reverse proxy)

```nginx
# /etc/nginx/sites-available/flowfusion
server {
    listen 80;
    server_name flowfusion.your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Включить сайт
sudo ln -s /etc/nginx/sites-available/flowfusion /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 4. Настроить HTTPS (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d flowfusion.your-domain.com
```

### 5. Запустить FlowFusion

```bash
# Скопировать конфиг
cp .env.example .env
nano .env  # Отредактировать значения

# Запустить
docker-compose -f docker-compose.prod.yml up -d

# Проверить
docker-compose -f docker-compose.prod.yml ps
```

### 6. Настроить автозапуск

```bash
# Создать systemd service
sudo nano /etc/systemd/system/flowfusion.service
```

```ini
[Unit]
Description=FlowFusion Backend
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/flowfusion
ExecStart=/usr/local/bin/docker-compose -f docker-compose.prod.yml up -d
ExecStop=/usr/local/bin/docker-compose -f docker-compose.prod.yml down

[Install]
WantedBy=multi-user.target
```

```bash
# Включить автозапуск
sudo systemctl enable flowfusion
sudo systemctl start flowfusion
sudo systemctl status flowfusion
```

---

## 📊 Мониторинг

### Проверка статуса

```bash
# Статус сервисов
docker-compose -f docker-compose.prod.yml ps

# Логи
docker-compose -f docker-compose.prod.yml logs -f api
docker-compose -f docker-compose.prod.yml logs -f worker
docker-compose -f docker-compose.prod.yml logs -f ollama

# Использование ресурсов
docker stats
```

### Health checks

```bash
# API health
curl https://flowfusion.your-domain.com/health

# Readiness (проверяет БД и Redis)
curl https://flowfusion.your-domain.com/ready
```

### Мониторинг очередей

```bash
# Проверить Redis очередь
docker-compose exec redis redis-cli -a ${REDIS_PASSWORD} LLEN event_queue

# Проверить необработанные события
docker-compose exec postgres psql -U ${DB_USER} -d ${DB_NAME} -c \
  "SELECT COUNT(*) FROM events WHERE processed = false;"
```

### Логи AI генерации

```bash
docker-compose logs worker --tail=100 | grep -E "(AI|Generating|summary)"
```

---

## 📈 Масштабирование

### Горизонтальное масштабирование worker

```bash
# Увеличить количество worker'ов до 4
docker-compose -f docker-compose.prod.yml up -d --scale worker=4

# Проверить
docker-compose ps
```

### Вертикальное масштабирование

Изменить в `docker-compose.prod.yml`:

```yaml
services:
  worker:
    deploy:
      resources:
        limits:
          cpus: '2'      # Увеличить CPU
          memory: 1G     # Увеличить RAM
```

### Масштабирование Ollama

Для production с высокой нагрузкой используйте облачный AI:

```bash
# В .env:
AI_PROVIDER=openrouter
AI_API_KEY=sk-or-xxxxxxxxxxxx
AI_MODEL=openai/gpt-4o-mini
AI_AUTO_GENERATE=true

# Затем в docker-compose.prod.yml закомментировать ollama service
```

---

## 🔧 Troubleshooting

### Worker не запускается

```bash
# Проверить логи
docker-compose logs worker

# Проверить переменные окружения
docker-compose exec worker env | grep AI_

# Перезапустить
docker-compose restart worker
```

### AI не генерирует

```bash
# Проверить Ollama
docker-compose exec ollama ollama list

# Протестировать Ollama
docker-compose exec ollama ollama run llama3.2 "Привет!"

# Проверить подключение из worker
docker-compose exec worker curl http://ollama:11434/api/tags
```

### Webhook не принимается

```bash
# Проверить токен
curl -X POST https://flowfusion.your-domain.com/webhooks/gitlab \
  -H "X-Gitlab-Token: wrong_token" \
  -d '{}'

# Ожидаемый ответ: 403 Forbidden

# Проверить правильный токен
curl -X POST https://flowfusion.your-domain.com/webhooks/gitlab \
  -H "X-Gitlab-Token: ${GITLAB_WEBHOOK_SECRET}" \
  -d '{"object_kind":"push"}'
```

### База данных не подключается

```bash
# Проверить PostgreSQL
docker-compose exec postgres pg_isready

# Проверить логи
docker-compose logs postgres

# Перезапустить
docker-compose restart postgres
```

### Redis не доступен

```bash
# Проверить Redis
docker-compose exec redis redis-cli ping

# Ожидаемый ответ: PONG

# Проверить с паролем
docker-compose exec redis redis-cli -a ${REDIS_PASSWORD} ping
```

---

## 📋 Production Checklist

- [ ] Все пароли изменены на безопасные
- [ ] GITLAB_WEBHOOK_SECRET установлен (32+ символа)
- [ ] HTTPS настроен (Let's Encrypt)
- [ ] Firewall настроен (только 22, 80, 443)
- [ ] Auto-restart настроен (systemd)
- [ ] Мониторинг настроен (health checks)
- [ ] Бэкапы настроены (PostgreSQL)
- [ ] Логирование включено (JSON format)
- [ ] AI протестирован (Ollama или cloud)
- [ ] Webhook протестирован (GitLab)

---

## 📞 Поддержка

При проблемах:

1. Проверьте логи: `docker-compose logs -f`
2. Проверьте health endpoints: `/health`, `/ready`
3. Проверьте переменные окружения: `docker-compose exec worker env`
4. Проверьте документацию: TROUBLESHOOTING.md

**FlowFusion готов к production!** 🚀
