# Руководство по тестированию

## Покрытие кода

**Общее покрытие: 81%**

| Компонент | Покрытие | Статус |
|-----------|----------|--------|
| `config.py` | 100% | ✅ |
| `logging_config.py` | 95% | ✅ |
| `models/__init__.py` | 94% | ✅ |
| `ai_summary_builder.py` | 99% | ✅ |
| `commit_aggregator.py` | 95% | ✅ |
| `event_queue_service.py` | 89% | ✅ |
| `webhook_integration.py` | 100% | ✅ |
| `processing_repository.py` | 85% | ✅ |
| `event_processor.py` | 71% | ⚠️ |
| `worker.py` | 57% | ⚠️ |
| `database.py` | 50% | ⚠️ |

## Запуск тестов

### Запустить все тесты
```bash
cd /Users/dmitriy/Documents/ai_concurs_backend
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -m pytest tests/ -v
```

### Запустить с отчётом о покрытии
```bash
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -m pytest tests/ --cov=app --cov-report=term-missing
```

### Запустить конкретный файл
```bash
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -m pytest tests/test_processing.py -v
```

### Запустить конкретный класс тестов
```bash
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -m pytest tests/test_processing_comprehensive.py::TestCommitAggregatorEdgeCases -v
```

### Запустить конкретную функцию теста
```bash
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -m pytest tests/test_processing.py::TestCommitAggregator::test_extract_jira_issue_from_branch -v
```

## Файлы тестов

### `tests/test_processing.py` (11 тестов)
Базовые unit-тесты для основных компонентов:
- `TestCommitAggregator` — извлечение Jira, фильтрация, группировка
- `TestAISummaryBuilder` — создание саммари, извлечение авторов
- `TestEventQueueService` — операции с очередью
- `TestProcessingRepository` — DB операции

### `tests/test_processing_comprehensive.py` (46 тестов)
Расширенные тесты граничных случаев:
- `TestCommitAggregatorEdgeCases` — парсинг веток, merge-коммиты, дубликаты
- `TestAISummaryBuilderEdgeCases` — очистка сообщений, авторы, временные диапазоны
- `TestEventQueueServiceFailures` — ошибки Redis, повторные попытки
- `TestProcessingRepositoryEdgeCases` — ошибки БД, пустые списки
- `TestEventProcessorPipeline` — полный поток обработки
- `TestFullPipelineIntegration` — end-to-end тесты

### `tests/test_integration.py` (28 тестов)
Интеграционные тесты и тесты worker:
- `TestWebhookIntegrationService` — интеграция с webhook
- `TestWorker` — инициализация и режимы worker
- `TestProcessEventJob` — обработка RQ-задач
- `TestEnqueueEvent` — постановка в очередь
- `TestEventQueueServiceAdditional` — дополнительные тесты очереди
- `TestCommitAggregatorTimeWindow` — батчинг по временному окну
- `TestAISummaryBuilderAdditional` — создание батчей
- `TestProcessingRepositoryAdditional` — дополнительные DB тесты

## Категории тестов

### Unit-тесты
Тестируют отдельные функции и методы в изоляции.

Пример:
```python
def test_extract_jira_issue_from_branch(self):
    result = self.aggregator.extract_jira_issue("feature/PROJ-123-login")
    assert result == "PROJ-123"
```

### Тесты граничных случаев
Тестируют граничные условия и необычные входные данные.

Пример:
```python
def test_filter_empty_message_commits(self):
    commits = [
        Commit(commit_id="1", message=""),
        Commit(commit_id="2", message="   "),
        Commit(commit_id="3", message=None),
    ]
    result = self.aggregator.filter_unprocessed_commits(commits, set())
    assert len(result) == 0
```

### Тесты обработки ошибок
Тестируют обработку ошибок и восстановление.

Пример:
```python
def test_process_event_with_exception(self):
    mock_repo.get_event.side_effect = Exception("DB error")
    result = processor.process_event(1)
    assert result is False
    mock_queue_service.retry_event.assert_called()
```

### Интеграционные тесты
Тестируют полный пайплайн от события до AI-саммари.

Пример:
```python
def test_commit_aggregator_full_flow(self):
    commits = [
        Commit(commit_id="1", message="Fix login", branch="feature/PROJ-123-login"),
        Commit(commit_id="2", message="Add retry", branch="feature/PROJ-123-login"),
    ]
    filtered = aggregator.filter_unprocessed_commits(commits, set())
    grouped = aggregator.group_by_jira_issue(filtered)
    assert "PROJ-123" in grouped
```

## Цели по покрытию

| Компонент | Текущее | Цель | Приоритет |
|-----------|---------|------|-----------|
| Логика обработки | 95%+ | 90% | ✅ Достигнуто |
| Сервис очереди | 89% | 85% | ✅ Достигнуто |
| Репозиторий | 85% | 80% | ✅ Достигнуто |
| Worker | 57% | 70% | ⚠️ Требуется работа |
| База данных | 50% | 70% | ⚠️ Требуется работа |

## Улучшение покрытия

Для улучшения покрытия `worker.py` и `database.py`:

1. **Тесты worker**: Добавить тесты для циклов `_run_direct_worker()` и `_run_rq_worker()`
2. **Тесты database**: Добавить тесты для контекстного менеджера `session_scope()`
3. **Тесты логирования**: Добавить тесты для конфигурации логирования

## Интеграция с CI/CD

Пример workflow для GitHub Actions:

```yaml
name: Тесты

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Установить Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - name: Установить зависимости
        run: pip install -r requirements.txt
      - name: Запустить тесты
        run: pytest tests/ --cov=app --cov-report=xml
      - name: Загрузить покрытие
        uses: codecov/codecov-action@v3
```

## Рекомендации по mocking

При написании тестов:

1. **Mock внешних зависимостей** (Redis, БД)
2. **Использовать декоратор `@patch`** для чистого mocking
3. **Проверять вызовы mock** для подтверждения поведения
4. **Тестировать пути успеха и ошибок**

Пример:
```python
@patch("app.processing.event_queue_service.redis.Redis")
def test_push_event(self, mock_redis_class):
    mock_redis = Mock()
    mock_redis_class.return_value = mock_redis
    mock_redis.sismember.return_value = False
    
    service = EventQueueService()
    result = service.push_event(42)
    
    assert result is True
    mock_redis.rpush.assert_called_once_with("event_queue", "42")
```
