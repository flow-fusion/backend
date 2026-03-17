# AI Concurs Backend — Слой обработки

Бэкенд-сервис для автоматического обновления задач Jira на основе Git-активности.

## Архитектура

```
GitLab Webhook → Событие в БД → Redis Queue → Worker → AI Summary → Jira (будущий слой)
```

## Компоненты

### EventQueueService
Управление очередями Redis для обработки событий:
- Основная очередь обработки
- Очередь повторных попыток с отложенной обработкой
- Очередь мёртвых писем для неудачных событий

### EventProcessor
Worker для обработки событий:
- Получает события из очереди
- Дедуплицирует коммиты
- Группирует по Jira-задачам
- Создаёт AI-саммари

### CommitAggregator
Группировка коммитов по Jira-задачам:
- Извлекает ключи Jira из имён веток
- Фильтрует обработанные/дублирующиеся коммиты
- Применяет батчинг по временному окну

### AISummaryBuilder
Подготовка данных для AI-обработки:
- Агрегирует сообщения коммитов
- Собирает метаданные (авторы, временной диапазон)
- Генерирует структурированный JSON для AI

## Установка

```bash
pip install -r requirements.txt
```

## Конфигурация

Скопируйте `.env.example` в `.env` и настройте:

```bash
cp .env.example .env
```

Основные настройки:
- `DATABASE_URL`: Строка подключения PostgreSQL
- `REDIS_HOST`, `REDIS_PORT`: Подключение к Redis
- `COMMIT_BATCH_WINDOW_MINUTES`: Временное окно для батчинга коммитов

## Запуск Worker

```bash
# Прямая опрос очереди (проще)
python -m app.workers.worker --direct

# Использование RQ (Redis Queue)
python -m app.workers.worker --use-rq
```

## Интеграция со слоем Webhook

После сохранения события в обработчике webhook:

```python
from app.processing.webhook_integration import queue_event

# Сохранение события в БД
event = Event(event_type="push", payload_json=payload)
session.add(event)
session.commit()

# Очередь на асинхронную обработку
queue_event(event.id)
```

## Схема базы данных

### events
- id, event_type, payload_json, created_at, processed, retry_count

### commits
- id, commit_id, message, author, timestamp, branch, repository, jira_issue, event_id, processed

### ai_summaries
- id, jira_issue, summary_input_json, created_at, processed, commit_count, time_range_start, time_range_end, authors

## Поток обработки

1. Webhook получает событие GitLab
2. Событие сохраняется в БД
3. ID события помещается в Redis queue
4. Worker получает событие из очереди
5. Worker загружает событие и коммиты из БД
6. Коммиты фильтруются (дедупликация)
7. Коммиты группируются по Jira-задачам
8. AI-саммари создаётся и сохраняется
9. Коммиты помечаются как обработанные
10. Событие помечается как обработанное

## Обработка ошибок

- Неудачные события повторяются до `MAX_RETRIES` раз
- После исчерпания попыток перемещаются в очередь мёртвых писем
- Все ошибки логируются с полными traceback

## Мониторинг

Статистика очередей доступна через:

```python
from app.processing.event_queue_service import EventQueueService

queue_service = EventQueueService()
stats = queue_service.get_queue_stats()
# Возвращает: main_queue_length, retry_queue_length, dead_letter_queue_length, currently_processing
```

## Тестирование

```bash
# Запустить все тесты
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -m pytest tests/ -v

# Запустить с покрытием
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -m pytest tests/ --cov=app --cov-report=term-missing
```

См. [TESTING.md](TESTING.md) для подробной информации о тестах.

## Будущее: Интеграция с Jira

Слой интеграции с Jira будет:
1. Читать таблицу `ai_summaries`
2. Генерировать текстовые саммари с помощью AI
3. Публиковать комментарии в задачи Jira
4. Помечать саммари как обработанные

## Структура проекта

```
ai_concurs_backend/
├── app/
│   ├── core/
│   │   ├── config.py           # Настройки приложения
│   │   ├── database.py         # Управление сессиями SQLAlchemy
│   │   └── logging_config.py   # Настройка JSON-логирования
│   ├── models/
│   │   └── __init__.py         # SQLAlchemy модели
│   ├── processing/
│   │   ├── event_queue_service.py  # Операции с Redis queue
│   │   ├── event_processor.py      # Логика worker
│   │   ├── commit_aggregator.py    # Группировка коммитов
│   │   ├── ai_summary_builder.py   # Подготовка данных для AI
│   │   └── webhook_integration.py  # Интеграция с webhook
│   ├── repositories/
│   │   └── processing_repository.py  # DB операции при обработке
│   └── workers/
│       └── worker.py           # Точка входа
├── tests/
│   ├── test_processing.py
│   ├── test_processing_comprehensive.py
│   └── test_integration.py
├── requirements.txt
├── .env.example
├── README.md
└── TESTING.md
```

## Производительность

Система рассчитана на обработку ~100 webhook-событий в минуту:
- Workers обрабатывают события конкурентно
- Используется pool workers
- Redis обеспечивает быструю очередь сообщений

## Лицензия

Внутренний проект.
