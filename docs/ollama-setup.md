# Ollama Setup Guide

Настройка локальной AI-модели Ollama для FlowFusion.

## Быстрый старт

```bash
# Запустить все сервисы
docker-compose up -d

# Скачать модель (llama3.2 рекомендуется)
docker-compose exec ollama ollama pull llama3.2

# Протестировать
docker-compose exec ollama ollama run llama3.2 "Привет!"
```

## Настройка

### 1. Включить AI в `.env`

```bash
AI_PROVIDER=ollama
AI_MODEL=llama3.2
AI_AUTO_GENERATE=true
OLLAMA_BASE_URL=http://ollama:11434
```

### 2. Перезапустить worker

```bash
docker-compose restart worker
```

## Доступные модели

| Модель | Размер | Качество | RAM |
|--------|--------|----------|-----|
| **llama3.2** | 3GB | ⭐⭐⭐ | 4 GB |
| **llama3.1:8b** | 8GB | ⭐⭐⭐⭐ | 8 GB |
| **mistral:7b** | 7GB | ⭐⭐⭐⭐ | 8 GB |
| **mixtral:8x7b** | 47GB | ⭐⭐⭐⭐⭐ | 32 GB |

### Скачать другую модель

```bash
docker-compose exec ollama ollama pull llama3.1:8b
```

Изменить в `.env`: `AI_MODEL=llama3.1:8b`

## Проверка работы

### 1. Отправить тестовый webhook

```bash
curl -X POST http://localhost:8000/webhooks/gitlab \
  -H "X-Gitlab-Token: test_secret" \
  -d '{"object_kind":"push","ref":"refs/heads/feature/PROJ-123","repository":{"name":"test"},"commits":[{"id":"abc","message":"Fix bug","author":{"name":"Test"},"timestamp":"2024-01-01T12:00:00Z"}]}'
```

### 2. Проверить логи

```bash
docker-compose logs worker | grep "AI"
```

### 3. Проверить результат в БД

```bash
docker-compose exec postgres psql -U postgres -d flowfusion -c "
SELECT jira_issue, summary_input_json->>'ai_generated_summary' as ai_summary
FROM ai_summaries ORDER BY id DESC LIMIT 1;
"
```

## Troubleshooting

**Ollama не запускается:**
```bash
docker-compose logs ollama
docker-compose restart ollama
```

**Модель не скачивается:**
```bash
docker-compose exec ollama ollama pull llama3.2
```

**AI не генерирует:**
```bash
# Проверить подключение
docker-compose exec worker curl http://ollama:11434/api/tags

# Проверить настройки
docker-compose exec worker env | grep AI_
```

**Мало памяти:** Используйте меньшую модель (`llama3.2` вместо `llama3.1:8b`)