# FlowFusion

Единый сервис для приёма GitLab webhook'ов, генерации AI-summary и автоматической синхронизации с Jira.

## Архитектура

Четырёхслойная архитектура:

```
┌─────────────────────────────────────────────────────────────┐
│                    WEBHOOK LAYER                            │
│  (app/webhooks/) — Приём и валидация HTTP-запросов          │
│  GitLab ──► routes.py ──► WebhookService ──► DB + Queue     │
└─────────────────────────────────────────────────────────────┘
                              │ queue_event()
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  PROCESSING LAYER                           │
│  (app/processing/) — Асинхронная обработка событий          │
│  Redis ──► EventProcessor ──► GitContext ──► AI Summary     │
└─────────────────────────────────────────────────────────────┘
                              │ ai_summaries table
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 JIRA INTEGRATION LAYER                      │
│  (app/jira_integration/) — Синхронизация с Jira             │
│  AI Summary ──► JiraClient ──► Comment + Transition         │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ использует
                              │
┌─────────────────────────────────────────────────────────────┐
│                    SHARED LAYER                             │
│  (app/shared/) — Общая инфраструктура                       │
│  ORM модели, Database, Configuration, Logging               │
└─────────────────────────────────────────────────────────────┘
```

## Быстрый старт

```bash
# Установить зависимости
pip install -r requirements.txt

# Скопировать конфигурацию
cp .env.example .env

# Запустить через Docker
docker-compose up -d

# Проверить
curl http://localhost:8000/health
```

## Документация

| Документ | Описание |
|----------|----------|
| [📚 AI Services](docs/ai-services.md) | Настройка AI-провайдеров (OpenAI, Anthropic, Ollama) |
| [🚀 Deployment](docs/deployment.md) | Развёртывание в production |
| [🤖 Ollama Setup](docs/ollama-setup.md) | Локальная AI-модель |
| [🔧 Troubleshooting](docs/troubleshooting.md) | Решение проблем |
| [📝 System Prompt](docs/system-prompt.md) | Промпт для генерации саммари |
| [🧪 Testing](docs/testing.md) | Запуск и структура тестов |

## Конфигурация

### Обязательные переменные

```bash
# GitLab
GITLAB_WEBHOOK_SECRET=your_webhook_secret_here
GITLAB_API_TOKEN=your_gitlab_api_token_here

# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/flowfusion

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# AI (опционально)
AI_PROVIDER=openrouter
AI_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxx
AI_MODEL=openai/gpt-4o-mini
AI_AUTO_GENERATE=true

# Jira (опционально)
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_TOKEN=your_jira_api_token
JIRA_AUTO_POST=true
```

Полный список: [.env.example](.env.example)

## Запуск

### FastAPI сервер (Webhook Layer)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Background Worker (Processing Layer)

```bash
python -m app.workers.worker --direct
```

### Оба процесса

```bash
# Terminal 1
uvicorn app.main:app --reload &

# Terminal 2
python -m app.workers.worker --direct &
```

## Поток данных

1. **Webhook получает событие:**
   ```
   GitLab ──► POST /webhooks/gitlab
                 ├─► Валидация токена
                 ├─► Парсинг payload
                 ├─► Извлечение Jira issue
                 ├─► Сохранение в БД
                 └─► queue_event() ──► Redis
   ```

2. **Worker обрабатывает:**
   ```
   Redis ──► EventProcessor
              ├─► Загрузка события и коммитов
              ├─► Загрузка Git-контекста
              ├─► Генерация AI-саммари
              └─► Сохранение в БД
   ```

3. **Jira интеграция:**
   ```
   AI Summary ──► JiraClient ──► Comment + Transition
   ```

## Интеграция с GitLab

1. Settings → Webhooks
2. URL: `https://your-server.com/webhooks/gitlab`
3. Secret Token: значение из `GITLAB_WEBHOOK_SECRET`
4. Trigger: Push events, Merge request events

### Тестовый запрос

```bash
curl -X POST http://localhost:8000/webhooks/gitlab \
  -H "X-Gitlab-Token: test_secret" \
  -d '{"object_kind":"push","ref":"refs/heads/feature/PROJ-123","repository":{"name":"test"},"commits":[{"id":"abc","message":"Fix","author":{"name":"Test"},"timestamp":"2024-01-01T12:00:00Z"}]}'
```

## Мониторинг

```bash
# Health checks
curl http://localhost:8000/health
curl http://localhost:8000/ready

# Логи
docker-compose logs -f api
docker-compose logs -f worker
```

## Структура проекта

```
root/
├── app/
│   ├── webhooks/              # Webhook layer
│   ├── processing/            # Processing layer
│   ├── shared/                # Shared layer
│   ├── jira_integration/      # Jira layer
│   └── main.py
├── tests/
├── docs/                      # Документация
├── docker-compose.yml
├── requirements.txt
└── README.md
```