# FlowFusion Troubleshooting Guide

## 📋 Оглавление

1. [Проблемы с Docker](#проблемы-с-docker)
2. [Проблемы с базой данных](#проблемы-с-базой-данных)
3. [Проблемы с импортами Python](#проблемы-с-импортами-python)
4. [Проблемы с webhook](#проблемы-с-webhook)
5. [Проблемы с worker](#проблемы-с-worker)
6. [Проблемы с Jira интеграцией](#проблемы-с-jira-интеграцией)
7. [Частые ошибки](#частые-ошибки)

---

## 🔧 Проблемы с Docker

### Docker daemon не запущен

**Ошибка:**
```
unable to get image 'redis:7-alpine': failed to connect to the docker API at unix:///var/run/docker.sock
```

**Решение:**
1. Откройте Docker Desktop
2. Дождитесь статуса "Docker Desktop is running"
3. Проверьте: `docker-compose ps`

---

### Контейнеры не создаются

**Ошибка:**
```
WARN: the attribute `version` is obsolete
```

**Решение:** Это предупреждение, не ошибка. Можно удалить `version: '3.8'` из `docker-compose.yml`.

---

### Порты заняты

**Ошибка:**
```
Error starting userland proxy: listen tcp 0.0.0.0:5432: bind: address already in use
```

**Решение:**
```bash
# Остановить локальную PostgreSQL
brew services stop postgresql

# Или изменить порт в docker-compose.yml
ports:
  - "5433:5432"  # Docker на 5433
```

---

## 🗄️ Проблемы с базой данных

### Таблицы не созданы

**Ошибка:**
```
(psycopg2.errors.UndefinedTable) relation "repositories" does not exist
```

**Решение:**
```bash
# Создать таблицы вручную
docker-compose exec postgres psql -U postgres -d flowfusion << 'EOF'
CREATE TABLE repositories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE branches (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    repository_id INTEGER REFERENCES repositories(id),
    jira_issue VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(name, repository_id)
);

CREATE TABLE commits (
    id SERIAL PRIMARY KEY,
    commit_hash VARCHAR(64) NOT NULL,
    branch_id INTEGER REFERENCES branches(id),
    author VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE,
    UNIQUE(commit_hash, branch_id)
);

CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    repository VARCHAR(255) NOT NULL,
    branch VARCHAR(255),
    jira_issue VARCHAR(50),
    author VARCHAR(255),
    payload_json TEXT NOT NULL,
    branch_id INTEGER REFERENCES branches(id),
    created_at TIMESTAMP DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE,
    processing_error TEXT,
    retry_count INTEGER DEFAULT 0
);

CREATE TABLE merge_requests (
    id SERIAL PRIMARY KEY,
    branch_id INTEGER REFERENCES branches(id),
    mr_id INTEGER NOT NULL,
    title VARCHAR(500),
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE ai_summaries (
    id SERIAL PRIMARY KEY,
    jira_issue VARCHAR(50) NOT NULL,
    summary_input_json JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP,
    jira_comment_id INTEGER,
    commit_count INTEGER,
    time_range_start TIMESTAMP,
    time_range_end TIMESTAMP,
    authors JSONB
);
EOF
```

---

### Колонки не совпадают с моделью

**Ошибка:**
```
AttributeError: type object 'Commit' has no attribute 'processed'
```

**Решение:**
1. Добавить колонку в БД:
```bash
docker-compose exec postgres psql -U postgres -d flowfusion -c "
ALTER TABLE commits ADD COLUMN IF NOT EXISTS processed BOOLEAN DEFAULT FALSE;
"
```

2. Обновить модель в `app/shared/models.py`:
```python
processed = Column(Boolean, default=False, nullable=False, index=True)
```

3. Перезапустить worker

---

### Неправильное подключение к БД

**Проблема:** Python подключается к локальной PostgreSQL вместо Docker

**Проверка:**
```bash
# Какие таблицы в Docker?
docker-compose exec postgres psql -U postgres -d flowfusion -c "SELECT tablename FROM pg_tables;"

# Какие таблицы в локальной?
psql postgres -d flowfusion -c "SELECT tablename FROM pg_tables;"
```

**Решение:**
```bash
# Остановить локальную PostgreSQL
brew services stop postgresql

# Перезапустить Docker контейнеры
docker-compose down
docker-compose up -d postgres redis

# Инициализировать БД
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -c "
from app.shared.database import init_db
init_db()
"
```

---

## 🐍 Проблемы с импортами Python

### ModuleNotFoundError: No module named 'app.core'

**Проблема:** Старые импорты после рефакторинга

**Решение:**
```bash
# Найти все старые импорты
grep -r "from app.core" app/ --include="*.py"

# Заменить на app.shared
find app/ -name "*.py" -exec sed -i '' 's/from app\.core/from app.shared/g' {} \;
```

---

### ModuleNotFoundError: No module named 'pythonjsonlogger'

**Проблема:** Зависимости не установлены

**Решение:**
```bash
python3 -m pip install -r requirements.txt
```

---

### Разные версии Python

**Проблема:** Зависимости установлены для Python 3.9, запускаете на 3.11

**Решение:**
```bash
# Проверить версию
python3 --version

# Установить для правильной версии
python3.11 -m pip install -r requirements.txt
```

---

## 🌐 Проблемы с webhook

### 401 Unauthorized

**Ошибка:**
```
{"detail":"Missing authentication token"}
```

**Решение:** Проверьте `GITLAB_WEBHOOK_SECRET` в `.env`:
```bash
# В .env:
GITLAB_WEBHOOK_SECRET=test_secret_for_local_dev

# В запросе:
-H "X-Gitlab-Token: test_secret_for_local_dev"
```

---

### 500 Internal Server Error: Missing required field: repository

**Проблема:** Неправильная структура payload

**Решение:**
```bash
# Правильно:
{
  "object_kind": "push",
  "repository": {"name": "test-repo"},  # ← На верхнем уровне!
  "commits": [...]
}

# Неправильно:
{
  "object_kind": "push",
  "commits": [...],
  "project": {"name": "test-repo"}  # ← Не работает!
}
```

---

### Failed to parse commit: Missing required field: timestamp

**Проблема:** GitLab всегда отправляет timestamp, но в тестовом запросе его нет

**Решение:**
```bash
# Добавьте timestamp в каждый коммит:
{
  "commits": [{
    "id": "abc123",
    "message": "Fix bug",
    "author": {"name": "Test"},
    "timestamp": "2024-01-01T12:00:00Z"  # ← Обязательно!
  }]
}
```

Или сделайте поле опциональным в парсере.

---

### Коммиты не создаются в БД

**Проблема:** Webhook возвращает 200 OK, но коммитов нет в БД

**Диагностика:**
```bash
# Проверить события
docker-compose exec postgres psql -U postgres -d flowfusion -c "
SELECT id, event_type, branch_id FROM events ORDER BY id DESC LIMIT 3;
"

# Проверить коммиты
docker-compose exec postgres psql -U postgres -d flowfusion -c "
SELECT id, commit_hash, branch_id FROM commits;
"
```

**Если branch_id разный:** Проблема в том что коммиты не сохраняются.

**Решение:** Добавить логирование в `app/webhooks/repositories/__init__.py`:
```python
def _store_commits(self, branch_id: int, commits: list) -> None:
    logger.debug(f"Storing {len(commits)} commits for branch {branch_id}")
    for commit_data in commits:
        commit = Commit(...)
        self.db.add(commit)
        logger.debug(f"Added commit {commit_data.commit_id[:8]}")
    self.db.flush()
    logger.info(f"Stored {len(commits)} commits successfully")
```

---

## ⚙️ Проблемы с worker

### ConnectionError: Error while reading from localhost:6379

**Проблема:** Redis не запущен или недоступен

**Решение:**
```bash
# Проверить Redis
docker-compose ps redis

# Перезапустить
docker-compose restart redis

# Проверить подключение
docker-compose exec redis redis-cli ping
# Должно вернуть: PONG
```

---

### AttributeError: 'Commit' object has no attribute 'commit_id'

**Проблема:** В модели поле называется `commit_hash`, а код использует `commit_id`

**Решение:** Найти и заменить все вхождения:
```bash
grep -r "commit\.commit_id" app/processing/ --include="*.py"
```

Заменить на `commit.commit_hash`:
```python
# app/processing/event_processor.py
dedup_key = f"{commit.commit_hash}:{branch_name}"
```

---

### Event scheduled for retry X/3

**Проблема:** Worker не может обработать событие

**Диагностика:**
```bash
# Посмотреть логи worker
# Искать: "Error processing event"

# Проверить событие в БД
docker-compose exec postgres psql -U postgres -d flowfusion -c "
SELECT id, event_type, processed, processing_error, retry_count 
FROM events 
WHERE retry_count > 0;
"
```

**Частые причины:**
1. Коммиты не найдены (проблема с branch_id)
2. Поля модели не совпадают с БД
3. Redis недоступен

---

### No Jira issue found in branch

**Проблема:** Ветка не содержит Jira ключ в формате `PROJ-123`

**Примеры:**
```
✅ feature/PROJ-123-login    → PROJ-123
✅ bugfix/ABC-456-fix        → ABC-456
❌ feature/PROJ-WITH-TIMESTAMP → None (нет цифр)
❌ feature/login-improvement → None (нет Jira ключа)
```

**Решение:** Использовать правильный формат веток:
```
feature/PROJ-123-description
```

Или изменить regex в `app/processing/commit_aggregator.py`:
```python
JIRA_ISSUE_PATTERN = re.compile(r'[A-Z]+-\d+')  # Только PROJ-123
```

---

## 🔗 Проблемы с Jira интеграцией

### 401 Unauthorized

**Проблема:** Неверный токен или email

**Решение:**
```bash
# Проверить curl:
curl -X GET "https://jira-test.eltc.ru/rest/api/3/myself" \
  -u "eftifanov.dv:ВАШ_ПАРОЛЬ" \
  -H "Accept: application/json"

# Если работает → использовать пароль в .env:
JIRA_TOKEN=ВАШ_ПАРОЛЬ
JIRA_USE_BEARER_AUTH=false
```

---

### 403 Forbidden

**Проблема:** Токен работает, но нет доступа к REST API

**Причины:**
1. REST API отключен в Jira
2. Нет прав на просмотр проекта
3. Неправильный URL

**Решение:**
1. Проверить URL: `https://jira-test.eltc.ru` (без `/secure/Dashboard.jspa`)
2. Попросить администратора включить REST API
3. Использовать пароль вместо токена

---

### 404 Not Found

**Проблема:** REST API отключен в Jira

**Проверка:**
```bash
curl -X GET "https://jira-test.eltc.ru/rest/api/3/serverInfo" \
  -u "username:password"
```

**Если 404:** REST API недоступен. Jira интеграция не будет работать.

**Решение:** Пропустить Jira интеграцию, AI-саммари будут сохраняться в БД.

---

## ⚠️ Частые ошибки

### psycopg2.OperationalError: connection refused

**Проблема:** PostgreSQL не запущен

**Решение:**
```bash
docker-compose up -d postgres
```

---

### redis.exceptions.ConnectionError

**Проблема:** Redis не запущен

**Решение:**
```bash
docker-compose up -d redis
```

---

### AttributeError: type object 'Commit' has no attribute 'event_id'

**Проблема:** В новой модели коммиты связаны с `branch`, а не с `event`

**Решение:** Обновить `get_unprocessed_commits_for_event`:
```python
# app/shared/processing_repository.py
def get_unprocessed_commits_for_event(self, event_id: int):
    event = self.get_event(event_id)
    if not event or not event.branch_id:
        return []
    
    commits = (
        self.session.query(Commit)
        .filter(
            and_(
                Commit.branch_id == event.branch_id,
                Commit.processed == False,
            )
        )
        .all()
    )
    return commits
```

---

### SQLAlchemy model doesn't match database table

**Проблема:** Модель обновлена, но БД нет

**Решение:**
1. Добавить колонку в БД:
```bash
docker-compose exec postgres psql -U postgres -d flowfusion -c "
ALTER TABLE commits ADD COLUMN processed BOOLEAN DEFAULT FALSE;
"
```

2. Обновить модель в `app/shared/models.py`

3. Перезапустить worker

---

### Worker processes event but no AI summary created

**Диагностика:**
```bash
# Проверить коммиты
docker-compose exec postgres psql -U postgres -d flowfusion -c "
SELECT id, commit_hash, branch_id, processed FROM commits;
"

# Проверить события
docker-compose exec postgres psql -U postgres -d flowfusion -c "
SELECT id, event_type, branch_id, processed FROM events;
"

# Проверить AI-саммари
docker-compose exec postgres psql -U postgres -d flowfusion -c "
SELECT id, jira_issue, commit_count FROM ai_summaries;
"
```

**Если коммиты есть, но AI-саммари нет:**
1. Проверить логи worker на ошибки
2. Проверить что `branch_id` совпадает в events и commits
3. Проверить что Jira issue извлекается из branch name

---

## 📞 Как получить помощь

### 1. Включить debug логи

В `.env`:
```bash
DEBUG=true
LOG_LEVEL=DEBUG
```

Перезапустить uvicorn и worker.

---

### 2. Проверить компоненты по отдельности

```bash
# Health check API
curl http://localhost:8000/health

# Проверить БД
docker-compose exec postgres psql -U postgres -d flowfusion -c "SELECT 1;"

# Проверить Redis
docker-compose exec redis redis-cli ping

# Проверить worker
# Смотрите логи в Terminal где запущен worker
```

---

### 3. Собрать информацию для отладки

```bash
# Версия Python
python3 --version

# Установленные пакеты
pip list | grep -E "(sqlalchemy|redis|fastapi|pydantic)"

# Статус контейнеров
docker-compose ps

# Таблицы в БД
docker-compose exec postgres psql -U postgres -d flowfusion -c "
SELECT tablename FROM pg_tables WHERE schemaname='public';
"

# Последние события
docker-compose exec postgres psql -U postgres -d flowfusion -c "
SELECT id, event_type, jira_issue, processed, created_at 
FROM events ORDER BY id DESC LIMIT 5;
"
```

---

## ✅ Чеклист успешной установки

- [ ] Docker Desktop запущен
- [ ] Контейнеры работают: `docker-compose ps`
- [ ] API отвечает: `curl http://localhost:8000/health`
- [ ] Worker запущен и слушает очередь
- [ ] Webhook принимает события: `curl -X POST /webhooks/gitlab ...`
- [ ] События обрабатываются (смотрите логи worker)
- [ ] AI-саммари создаются (проверьте таблицу `ai_summaries`)

---

**133 теста проходят** ✅

**FlowFusion полностью работает!** 🚀
