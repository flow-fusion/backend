# FlowFusion

Единый сервис для приёма GitLab webhook'ов, генерации AI-summary и автоматической синхронизации с Jira.

## Архитектура

Проект использует **четырёхслойную архитектуру**:

```
┌─────────────────────────────────────────────────────────────┐
│                    WEBHOOK LAYER                            │
│  (app/webhooks/) — Приём и валидация HTTP-запросов          │
│                                                             │
│  GitLab ──► routes.py ──► WebhookService ──► DB + Queue     │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ queue_event()
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  PROCESSING LAYER                           │
│  (app/processing/) — Асинхронная обработка событий          │
│                                                             │
│  Redis ──► EventProcessor ──► GitContext ──► AI Summary     │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ ai_summaries table
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 JIRA INTEGRATION LAYER                      │
│  (app/jira_integration/) — Синхронизация с Jira             │
│                                                             │
│  AI Summary ──► JiraClient ──► Comment + Transition         │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ использует
                              │
┌─────────────────────────────────────────────────────────────┐
│                    SHARED LAYER                             │
│  (app/shared/) — Общая инфраструктура                       │
│                                                             │
│  - ORM модели (Event, Commit, Branch...)                    │
│  - Database connection                                      │
│  - Configuration                                            │
│  - Logging                                                  │
└─────────────────────────────────────────────────────────────┘
```

## Структура проекта

```
root/
├── app/
│   ├── webhooks/              # WEBHOOK LAYER
│   │   ├── __init__.py
│   │   ├── routes.py          # FastAPI endpoints (/webhooks/gitlab)
│   │   ├── models/
│   │   │   └── __init__.py    # Dataclasses: NormalizedEvent, GitLabCommit
│   │   ├── services/
│   │   │   ├── __init__.py    # WebhookService (бизнес-логика webhook)
│   │   │   └── gitlab_parser.py  # Парсинг payload GitLab
│   │   └── repositories/
│   │       └── __init__.py    # WebhookRepository (сохранение в БД)
│   │
│   ├── processing/            # PROCESSING LAYER
│   │   ├── __init__.py
│   │   ├── event_processor.py       # Worker: обработка из очереди
│   │   ├── event_queue_service.py   # Redis queue operations
│   │   ├── commit_aggregator.py     # Группировка по Jira
│   │   ├── ai_summary_builder.py    # Подготовка данных для AI
│   │   ├── git_context_service.py   # GitLab API (файлы, diff, MR)
│   │   └── webhook_integration.py   # Точка интеграции: queue_event()
│   │
│   ├── shared/                # SHARED LAYER
│   │   ├── __init__.py
│   │   ├── config.py          # Конфигурация приложения
│   │   ├── database.py        # DB connection, sessions
│   │   ├── logging_config.py  # Логирование
│   │   ├── models.py          # SQLAlchemy ORM модели
│   │   ├── processing_repository.py  # DB операции для processing
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── jira_key_extractor.py  # Извлечение Jira keys
│   │
│   ├── workers/               # WORKER ENTRY POINT
│   │   ├── __init__.py
│   │   └── worker.py          # Background worker
│   │
│   ├── jira_integration/      # JIRA INTEGRATION LAYER
│   │   ├── __init__.py
│   │   ├── config.py          # Jira configuration
│   │   ├── jira_client.py     # Jira API client
│   │   └── mr_processor.py    # MR processor with Jira sync
│   │
│   └── main.py                # FastAPI приложение
│
├── tests/                     # Тесты (137 тестов)
│   ├── test_processing.py
│   ├── test_processing_comprehensive.py
│   ├── test_integration.py
│   ├── test_git_context.py
│   └── test_jira_integration.py
│
├── requirements.txt
├── .env.example
├── README.md
└── TESTING.md
```

## Установка

```bash
cd /Users/dmitriy/Documents/flow-fusion

# Установить зависимости
pip install -r requirements.txt

# Скопировать конфигурацию
cp .env.example .env

# Отредактировать .env (обязательно задать секреты!)
```

## Конфигурация

### Обязательные переменные окружения

```bash
# GitLab Webhook (ОБЯЗАТЕЛЬНО!)
GITLAB_WEBHOOK_SECRET=your_webhook_secret_here

# GitLab API (для enrichment AI-саммари)
GITLAB_API_TOKEN=your_gitlab_api_token_here

# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/flow-fusion

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Jira (ОПЦИОНАЛЬНО - для авто-постинга в Jira)
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_TOKEN=your_jira_api_token
JIRA_AUTO_POST=true  # Включить авто-постинг в Jira
```

### Полный список настроек

См. `.env.example`:
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_HOST`, `REDIS_PORT` — Redis connection
- `GITLAB_WEBHOOK_SECRET` — Secret для валидации webhook'ов
- `GITLAB_API_TOKEN` — Token для доступа к GitLab API
- `GITLAB_BASE_URL` — URL GitLab (по умолчанию https://gitlab.com)
- `COMMIT_BATCH_WINDOW_MINUTES` — Временное окно для батчинга коммитов
- `LOG_LEVEL` — Уровень логирования

## Запуск

### 1. FastAPI сервер (Webhook Layer)

Принимает запросы от GitLab:

```bash
cd /Users/dmitriy/Documents/ai_concurs_backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Доступные endpoints:
- `POST /webhooks/gitlab` — GitLab webhook endpoint
- `GET /health` — Health check
- `GET /ready` — Readiness check
- `GET /docs` — Swagger UI

### 2. Background Worker (Processing Layer)

Обрабатывает события из очереди:

```bash
cd /Users/dmitriy/Documents/ai_concurs_backend
python -m app.workers.worker --direct
```

Или с использованием RQ:
```bash
python -m app.workers.worker --use-rq
```

### 3. Оба процесса одновременно (для разработки)

```bash
# Terminal 1
uvicorn app.main:app --reload &

# Terminal 2
python -m app.workers.worker --direct &
```

## Поток данных

### 1. Webhook получает событие

```
GitLab ──► POST /webhooks/gitlab
              │
              ├─► Валидация токена (X-Gitlab-Token)
              ├─► Парсинг payload (GitLabParser)
              ├─► Извлечение Jira issue из branch name
              ├─► Сохранение в БД (Event, Commit, Branch, MR)
              └─► queue_event(event_id) ──► Redis
```

### 2. Worker обрабатывает событие

```
Redis ──► EventProcessor.process_event()
              │
              ├─► Загрузка события из БД
              ├─► Загрузка коммитов
              ├─► Фильтрация обработанных коммитов
              ├─► Группировка по Jira issue (CommitAggregator)
              │
              ├─► Загрузка Git-контекста (GitContextService)
              │   ├─► Изменённые файлы
              │   ├─► Diff summary (+N строк, -N строк)
              │   └─► Merge Request info (title, description, author)
              │
              ├─► Построение AI-саммари (AISummaryBuilder)
              └─► Сохранение в ai_summaries (БД)
```

### 3. AI-саммари готово для Jira

Таблица `ai_summaries` содержит структурированные данные:

```json
{
  "jira_issue": "PROJ-123",
  "commit_messages": ["Fix login bug", "Add retry logic"],
  "authors": ["Ivan"],
  "changed_files": ["auth_service.py", "login_controller.ts"],
  "diff_summary": [
    "auth_service.py: +20 lines added, -3 lines removed",
    "login_controller.ts: +15 lines added"
  ],
  "merge_request_title": "Fix login redirect bug",
  "merge_request_description": "This MR fixes...",
  "time_range": {
    "start": "2024-01-15T10:00:00",
    "end": "2024-01-15T10:30:00"
  }
}
```

## Тестирование

```bash
cd /Users/dmitriy/Documents/ai_concurs_backend

# Запустить все тесты
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -m pytest tests/ -v

# Запустить с покрытием
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -m pytest tests/ --cov=app --cov-report=term-missing

# Запустить конкретный тест
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -m pytest tests/test_processing.py -v
```

## 🔧 Troubleshooting

Если возникли проблемы, смотрите [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

### Частые проблемы:

| Ошибка | Решение |
|--------|---------|
| `ModuleNotFoundError: No module named 'app.core'` | Заменить на `app.shared` |
| `relation "repositories" does not exist` | Создать таблицы в БД |
| `AttributeError: 'Commit' object has no attribute 'commit_id'` | Использовать `commit_hash` |
| `Failed to parse commit: Missing required field: timestamp` | Добавить `timestamp` в webhook payload |
| `401 Unauthorized` (Jira) | Использовать пароль вместо токена |
| `403 Forbidden` (Jira) | REST API отключен, пропустить Jira интеграцию |
| `Connection refused` (Redis/Postgres) | Запустить `docker-compose up -d` |

## Интеграция с GitLab

### 1. Настройте webhook в GitLab

1. Зайдите в проект GitLab
2. Settings → Webhooks
3. URL: `https://your-server.com/webhooks/gitlab`
4. Secret Token: `<your_secret_from_env>`
5. Trigger: Push events, Merge request events
6. Enable SSL verification (если используется HTTPS)

### 2. Проверьте работу

```bash
# Тестовый запрос
curl -X POST http://localhost:8000/webhooks/gitlab \
  -H "Content-Type: application/json" \
  -H "X-Gitlab-Event: Push Hook" \
  -H "X-Gitlab-Token: your_secret" \
  -d '{
    "object_kind": "push",
    "ref": "refs/heads/feature/PROJ-123-test",
    "project": {"name": "my-repo"},
    "commits": [{
      "id": "abc123",
      "message": "Fix bug",
      "author": {"name": "Ivan"},
      "timestamp": "2024-01-15T10:00:00Z"
    }]
  }'
```

Ожидаемый ответ:
```json
{
  "status": "success",
  "event_id": "42",
  "event_type": "push",
  "repository": "my-repo",
  "jira_issue": "PROJ-123"
}
```

## Мониторинг

### Health checks

```bash
# Health
curl http://localhost:8000/health
# {"status": "healthy"}

# Readiness
curl http://localhost:8000/ready
# {"status": "ready"}
```

### Логирование

Логи выводятся в stdout в формате:
```
2024-01-15T10:00:00+0000 - ai_concurs.webhooks - INFO - Received push event | repo=my-repo | branch=feature/PROJ-123 | jira=PROJ-123 | commits=3
2024-01-15T10:00:01+0000 - ai_concurs.event_processor - INFO - Processing event id=42
2024-01-15T10:00:02+0000 - ai_concurs.git_context_service - INFO - Loaded Git context: 3 files, 3 diff summaries, MR: Fix login
2024-01-15T10:00:03+0000 - ai_concurs.event_processor - INFO - Successfully processed event 42
```

### Статистика очередей

```python
from app.processing.event_queue_service import EventQueueService

queue_service = EventQueueService()
stats = queue_service.get_queue_stats()
# {
#   "main_queue_length": 5,
#   "retry_queue_length": 2,
#   "dead_letter_queue_length": 0,
#   "currently_processing": 1
# }
```

## Обработка ошибок

### Webhook layer

- Неверный токен → HTTP 403
- Невалидный payload → HTTP 400
- Ошибка БД → HTTP 500 + rollback

### Processing layer

- Ошибка обработки → retry (до 3 раз)
- Исчерпаны retry → dead letter queue
- GitLab API недоступен → продолжение без Git context

## Будущее расширение

### Jira Integration Layer

Следующий слой будет:
1. Читать из `ai_summaries` table
2. Генерировать текстовые саммари через AI (LLM)
3. Постить комментарии в Jira
4. Помечать `ai_summaries.processed = true`

### API для запросов

Добавить REST API для запросов:
- `GET /events/{id}` — статус обработки события
- `GET /jira/{issue}/summaries` — саммари по Jira issue
- `GET /summaries/pending` — необработанные саммари

## Лицензия

Внутренний проект.
