# Testing Guide

Руководство по тестированию FlowFusion.

## Запуск тестов

### Все тесты

```bash
cd /Users/dmitriy/Documents/ai_concurs_backend
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -m pytest tests/ -v
```

### С покрытием

```bash
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -m pytest tests/ --cov=app --cov-report=term-missing
```

### Конкретный тест

```bash
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -m pytest tests/test_processing.py -v
```

### Конкретный класс тестов

```bash
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -m pytest tests/test_jira_integration.py::TestJiraClient -v
```

## Структура тестов

| Файл | Описание | Тестов |
|------|----------|--------|
| `test_webhook_integration.py` | Webhook layer, Worker, EventQueueService | 24 |
| `test_processing.py` | CommitAggregator, AISummaryBuilder, ProcessingRepository | 11 |
| `test_processing_comprehensive.py` | Edge cases, failure scenarios, pipeline | 35 |
| `test_git_context.py` | GitContextService, GitLab API mocking | 32 |
| `test_jira_integration.py` | JiraClient, MRProcessor | 23 |
| `test_jira_only.py` | Standalone скрипт проверки Jira подключения | - |

**Всего: 133 теста** ✅

## Что тестируется

### Webhook Layer

- Приём и валидация webhook'ов
- Queue operations (push/pop/retry)
- Worker initialization и lifecycle

### Processing Layer

- Извлечение Jira issue из branch name
- Фильтрация коммитов (merge, empty, processed)
- Группировка по Jira и временным окнам
- Генерация AI summary input
- Event processing pipeline

### Git Context Service

- Загрузка diff из GitLab API
- Парсинг merge request info
- Кэширование и retry logic

### Jira Integration

- Получение задач и комментариев
- Transition между статусами
- Rate limiting и retry logic
- MR processor с Jira sync

## Мокирование

Тесты используют моки для:
- Redis (очереди)
- PostgreSQL (ORM сессии)
- HTTP запросов (GitLab/Jira API)

## Troubleshooting

**ModuleNotFoundError:** Убедитесь что PYTHONPATH установлен:
```bash
export PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend
```

**Import errors:** Запускайте из корня проекта:
```bash
cd /Users/dmitriy/Documents/ai_concurs_backend
```
