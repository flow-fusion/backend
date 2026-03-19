# Troubleshooting Guide

## Docker

**Контейнеры не запускаются:**
```bash
docker-compose ps
docker-compose logs
docker-compose restart
```

**Порты заняты:**
```bash
# Остановить локальную PostgreSQL
brew services stop postgresql

# Или изменить порт в docker-compose.yml
ports:
  - "5433:5432"
```

## База данных

**Таблицы не существуют:**
```bash
docker-compose exec postgres psql -U postgres -d flowfusion << 'EOF'
CREATE TABLE IF NOT EXISTS repositories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);
-- (остальные таблицы аналогично)
EOF
```

**Неправильное подключение:**
```bash
# Остановить локальную PostgreSQL
brew services stop postgresql

# Перезапустить Docker
docker-compose down && docker-compose up -d postgres
```

## Импорты Python

**ModuleNotFoundError: No module named 'app.core':**
```bash
# Заменить старые импорты
find app/ -name "*.py" -exec sed -i '' 's/from app\.core/from app.shared/g' {} \;
```

## Webhook

**401 Unauthorized:** Проверьте `GITLAB_WEBHOOK_SECRET` в `.env` и заголовке `X-Gitlab-Token`

**500 Internal Server Error:** Проверьте структуру payload:
```json
{
  "object_kind": "push",
  "repository": {"name": "test-repo"},
  "commits": [{"id": "abc", "message": "Fix", "author": {"name": "Test"}, "timestamp": "2024-01-01T12:00:00Z"}]
}
```

## Worker

**ConnectionError к Redis:**
```bash
docker-compose restart redis
docker-compose exec redis redis-cli ping  # Должно вернуть PONG
```

**Event scheduled for retry:** Проверьте логи worker на "Error processing event"

**No Jira issue found:** Ветка должна содержать `PROJ-123` (например, `feature/PROJ-123-login`)

## Jira

**401 Unauthorized:** Проверьте `JIRA_TOKEN` и `JIRA_EMAIL`

**403 Forbidden:** REST API отключен в Jira или нет прав доступа

**404 Not Found:** REST API недоступен. Пропустите Jira интеграцию.

## AI

**AI summary не генерируется:**
1. Проверьте `AI_AUTO_GENERATE=true`
2. Проверьте API ключ
3. Проверьте подключение к интернету

**Ollama не работает:**
```bash
docker-compose exec ollama ollama list
docker-compose exec ollama ollama run llama3.2 "Привет!"
```

## Диагностика

```bash
# Health check
curl http://localhost:8000/health

# Проверить БД
docker-compose exec postgres psql -U postgres -d flowfusion -c "SELECT 1;"

# Проверить Redis
docker-compose exec redis redis-cli ping

# Посмотреть последние события
docker-compose exec postgres psql -U postgres -d flowfusion -c \
  "SELECT id, event_type, jira_issue, processed FROM events ORDER BY id DESC LIMIT 5;"
```
