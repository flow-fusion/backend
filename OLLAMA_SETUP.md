# FlowFusion с Ollama (Local LLM)

Полное руководство по настройке локальной AI-модели в Docker.

---

## 📋 Оглавление

1. [Быстрый старт](#быстрый-старт)
2. [Настройка Ollama](#настройка-ollama)
3. [Включение AI-генерации](#включение-ai-генерации)
4. [Проверка работы](#проверка-работы)
5. [Требования к ресурсам](#требования-к-ресурсам)
6. [Troubleshooting](#troubleshooting)

---

## 🚀 Быстрый старт

### 1. Запустить все сервисы

```bash
cd /Users/dmitriy/Documents/ai_concurs_backend

# Запустить PostgreSQL, Redis, Ollama, API и Worker
docker-compose up -d
```

### 2. Настроить Ollama

```bash
# Запустить скрипт настройки
./scripts/setup-ollama.sh
```

Или вручную:

```bash
# Дождаться пока Ollama запустится
docker-compose ps

# Скачать модель
docker-compose exec ollama ollama pull llama3.2
```

### 3. Включить AI (опционально)

В `.env`:

```bash
AI_AUTO_GENERATE=true
```

Перезапустить worker:

```bash
docker-compose restart worker
```

---

## 📦 Настройка Ollama

### Какие модели доступны?

| Модель | Размер | Качество | Скорость | RAM |
|--------|--------|----------|----------|-----|
| **llama3.2** | 3B | ⭐⭐⭐ | ⚡⚡⚡⚡⚡ | 4GB |
| **llama3.1:8b** | 8B | ⭐⭐⭐⭐ | ⚡⚡⚡⚡ | 8GB |
| **mistral:7b** | 7B | ⭐⭐⭐⭐ | ⚡⚡⚡⚡ | 8GB |
| **mixtral:8x7b** | 47B | ⭐⭐⭐⭐⭐ | ⚡⚡⚡ | 32GB |

### Скачать модель

```bash
# llama3.2 (рекомендуется для начала)
docker-compose exec ollama ollama pull llama3.2

# llama3.1 8B (лучшее качество)
docker-compose exec ollama ollama pull llama3.1:8b

# Mistral 7B (альтернатива)
docker-compose exec ollama ollama pull mistral:7b
```

### Изменить модель

В `.env`:

```bash
AI_MODEL=llama3.1:8b
```

Перезапустить:

```bash
docker-compose restart api worker
```

---

## ✅ Включение AI-генерации

### 1. Проверить что Ollama работает

```bash
docker-compose exec ollama ollama list
```

**Ожидаемый вывод:**
```
NAME            ID              SIZE      MODIFIED
llama3.2:latest a80c153ef53c    2.0 GB    2 minutes ago
```

### 2. Протестировать модель

```bash
docker-compose exec ollama ollama run llama3.2 "Привет! Как дела?"
```

**Ожидаемый ответ:**
```
Привет! У меня всё хорошо, спасибо. Как я могу помочь вам сегодня?
```

### 3. Включить AI в FlowFusion

В `.env`:

```bash
AI_PROVIDER=ollama
AI_MODEL=llama3.2
AI_AUTO_GENERATE=true
OLLAMA_BASE_URL=http://ollama:11434
```

### 4. Перезапустить worker

```bash
docker-compose restart worker
```

---

## 🔍 Проверка работы

### 1. Отправить тестовый webhook

```bash
curl -X POST http://localhost:8000/webhooks/gitlab \
  -H "Content-Type: application/json" \
  -H "X-Gitlab-Event: Push Hook" \
  -H "X-Gitlab-Token: test_secret" \
  -d '{
    "object_kind": "push",
    "ref": "refs/heads/feature/PROJ-123-test",
    "repository": {"name": "test-repo"},
    "commits": [{
      "id": "abc123",
      "message": "Fix critical bug in authentication",
      "author": {"name": "Test User"},
      "timestamp": "2024-01-01T12:00:00Z"
    }]
  }'
```

### 2. Проверить логи worker

```bash
docker-compose logs -f worker | grep "AI"
```

**Ожидаемые логи:**
```
INFO - Generating AI summary for Jira issue PROJ-123
INFO - AI summary generated: 250 chars
INFO - Successfully processed event 11
```

### 3. Проверить AI-саммари в БД

```bash
docker-compose exec postgres psql -U postgres -d flowfusion -c "
SELECT 
    jira_issue,
    summary_input_json->>'ai_generated_summary' as ai_summary
FROM ai_summaries
ORDER BY id DESC LIMIT 1;
"
```

**Ожидаемый результат:**
```
 jira_issue |                           ai_summary                            
------------+-------------------------------------------------------------------
 PROJ-123   | ✅ Выполнена работа по задаче PROJ-123:                          +
            |                                                                   +
            | Проведена критическая правка в модуле аутентификации.            +
            | Исправлена ошибка, влияющая на безопасность системы.             +
            |                                                                   +
            | Автор: Test User                                                  +
            | Merge Request готов к ревью.
```

---

## 💾 Требования к ресурсам

### Минимальные (llama3.2):

| Ресурс | Требование |
|--------|------------|
| **CPU** | 2 cores |
| **RAM** | 4 GB |
| **Storage** | 5 GB |

### Рекомендуемые (llama3.1:8b):

| Ресурс | Требование |
|--------|------------|
| **CPU** | 4 cores |
| **RAM** | 8 GB |
| **Storage** | 10 GB |

### Для больших моделей (mixtral:8x7b):

| Ресурс | Требование |
|--------|------------|
| **CPU** | 8+ cores |
| **RAM** | 32 GB |
| **Storage** | 50 GB |

---

## ⚙️ Docker Compose конфигурация

### Development (docker-compose.yml)

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: flowfusion-ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        limits:
          memory: 4G  # Увеличить для больших моделей
```

### Production (docker-compose.prod.yml)

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: flowfusion-ollama
    volumes:
      - ollama_data:/root/.ollama
    networks:
      - flowfusion-internal  # Не открывать наружу!
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 8G
```

---

## 🔧 Troubleshooting

### Ollama не запускается

**Проверьте логи:**
```bash
docker-compose logs ollama
```

**Перезапустите:**
```bash
docker-compose restart ollama
```

---

### Модель не скачивается

**Проверьте подключение:**
```bash
docker-compose exec ollama curl -I https://ollama.ai
```

**Попробуйте другую модель:**
```bash
docker-compose exec ollama ollama pull mistral:7b
```

---

### AI summary не генерируется

**Проверьте настройки:**
```bash
docker-compose exec worker env | grep AI_
```

**Ожидаемый вывод:**
```
AI_PROVIDER=ollama
AI_MODEL=llama3.2
AI_AUTO_GENERATE=true
OLLAMA_BASE_URL=http://ollama:11434
```

**Проверьте подключение к Ollama:**
```bash
docker-compose exec worker curl http://ollama:11434/api/tags
```

---

### "Error: model not found"

**Скачайте модель:**
```bash
docker-compose exec ollama ollama pull llama3.2
```

**Проверьте список:**
```bash
docker-compose exec ollama ollama list
```

---

### Ollama потребляет много RAM

**Используйте меньшую модель:**
```bash
# Вместо llama3.1:8b используйте llama3.2
docker-compose exec ollama ollama pull llama3.2
```

**Ограничьте память в docker-compose.yml:**
```yaml
services:
  ollama:
    deploy:
      resources:
        limits:
          memory: 4G  # Уменьшить с 8G
```

---

### AI генерирует на английском вместо русского

**Проблема:** Модель не следует инструкции

**Решение:** Изменить системный промпт в `app/processing/ai_service.py`:

```python
def _get_system_prompt(self) -> str:
    return """Ты — помощник для генерации профессиональных прогресс-апдейтов для Jira задач.

Всегда отвечай на РУССКОМ языке.
```

Или используйте модель с лучшей поддержкой русского:
```bash
docker-compose exec ollama ollama pull saiga  # Русскоязычная Llama
```

---

## 📊 Сравнение: Cloud AI vs Local Ollama

| Критерий | Cloud (OpenAI) | Local (Ollama) |
|----------|----------------|----------------|
| **Стоимость** | $0.15/1M tokens | $0 (бесплатно) |
| **Качество** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Скорость** | ~1 сек | ~5-10 сек |
| **Приватность** | Данные у провайдера | Полная приватность |
| **Требования** | Интернет | CPU/RAM локально |
| **Настройка** | 5 минут | 15 минут |

---

## 🎯 Рекомендации

### Для разработки:

```bash
AI_PROVIDER=ollama
AI_MODEL=llama3.2
AI_AUTO_GENERATE=false  # Включить когда нужно
```

### Для production (если нет облачного AI):

```bash
AI_PROVIDER=ollama
AI_MODEL=llama3.1:8b
AI_AUTO_GENERATE=true
```

### Для production (рекомендуется облачный AI):

```bash
AI_PROVIDER=openrouter
AI_MODEL=openai/gpt-4o-mini
AI_AUTO_GENERATE=true
```

---

## 📞 Поддержка

При проблемах:

1. Проверьте логи: `docker-compose logs ollama worker`
2. Проверьте ресурсы: `docker stats flowfusion-ollama`
3. Перезапустите Ollama: `docker-compose restart ollama`
4. Перекачайте модель: `docker-compose exec ollama ollama pull llama3.2`

**FlowFusion с Ollama полностью работает!** 🚀
