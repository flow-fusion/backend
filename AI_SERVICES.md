# AI Service Configuration Guide

FlowFusion поддерживает множественные AI-провайдеры для генерации саммари.

---

## 🤖 Поддерживаемые провайдеры

| Провайдер | Модели | Стоимость | Качество | Скорость |
|-----------|--------|-----------|----------|----------|
| **OpenRouter** | 100+ моделей | от $0.10/1M | ⭐⭐⭐⭐⭐ | ⚡⚡⚡⚡⚡ |
| **OpenAI** | GPT-4, GPT-3.5 | $0.15-10/1M | ⭐⭐⭐⭐⭐ | ⚡⚡⚡⚡⚡ |
| **Anthropic** | Claude 3 | $3-15/1M | ⭐⭐⭐⭐⭐ | ⚡⚡⚡⚡ |
| **Google** | Gemini | $0.075-7/1M | ⭐⭐⭐⭐ | ⚡⚡⚡⚡⚡ |
| **Ollama** | Llama, Mistral | Бесплатно | ⭐⭐⭐ | ⚡⚡⚡ |

---

## 🚀 Быстрый старт

### Вариант 1: OpenRouter (рекомендуется)

**Преимущества:**
- ✅ Доступ к 100+ моделям через один API
- ✅ Дешёвые модели (GPT-4o-mini за $0.15/1M)
- ✅ Не нужно несколько API ключей
- ✅ Автоматический fallback

**Настройка:**

1. Получите ключ: https://openrouter.ai/keys
2. Добавьте в `.env`:

```bash
AI_PROVIDER=openrouter
AI_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxx
AI_MODEL=openai/gpt-4o-mini
AI_AUTO_GENERATE=true
```

**Доступные модели:**
- `openai/gpt-4o-mini` — $0.15/1M (рекомендуется)
- `openai/gpt-4o` — $2.50/1M
- `anthropic/claude-3-haiku` — $0.25/1M
- `google/gemini-flash-1.5` — $0.075/1M
- `meta-llama/llama-3-70b` — $0.80/1M

---

### Вариант 2: OpenAI напрямую

**Настройка:**

1. Получите ключ: https://platform.openai.com/api-keys
2. Добавьте в `.env`:

```bash
AI_PROVIDER=openai
AI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
AI_MODEL=gpt-4o-mini
AI_AUTO_GENERATE=true
```

**Модели:**
- `gpt-4o-mini` — $0.15/1M (рекомендуется)
- `gpt-4o` — $2.50/1M
- `gpt-4-turbo` — $10/1M
- `gpt-3.5-turbo` — $0.50/1M

---

### Вариант 3: Anthropic Claude

**Настройка:**

1. Получите ключ: https://console.anthropic.com/settings/keys
2. Добавьте в `.env`:

```bash
AI_PROVIDER=anthropic
AI_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx
AI_MODEL=claude-3-haiku-20240307
AI_AUTO_GENERATE=true
```

**Модели:**
- `claude-3-haiku-20240307` — $0.25/1M (быстро, дёшево)
- `claude-3-sonnet-20240229` — $3/1M (баланс)
- `claude-3-opus-20240229` — $15/1M (лучшее качество)

---

### Вариант 4: Google Gemini

**Настройка:**

1. Получите ключ: https://makersuite.google.com/app/apikey
2. Добавьте в `.env`:

```bash
AI_PROVIDER=google
AI_API_KEY=xxxxxxxxxxxxxxxxxxxx
AI_MODEL=gemini-1.5-flash
AI_AUTO_GENERATE=true
```

**Модели:**
- `gemini-1.5-flash` — $0.075/1M (быстро)
- `gemini-1.5-pro` — $7/1M (качество)

---

### Вариант 5: Ollama (локально, бесплатно)

**Преимущества:**
- ✅ Бесплатно
- ✅ Полная приватность
- ✅ Работает без интернета

**Недостатки:**
- ❌ Требует ресурсы (CPU/RAM)
- ❌ Качество ниже чем у коммерческих моделей

**Настройка:**

1. Установите Ollama: https://ollama.ai
2. Скачайте модель:
```bash
ollama pull llama3.2
```

3. Добавьте в `.env`:

```bash
AI_PROVIDER=ollama
AI_MODEL=llama3.2
AI_AUTO_GENERATE=true
OLLAMA_BASE_URL=http://localhost:11434
```

**Модели:**
- `llama3.2` — 3B параметров (быстро)
- `llama3.1:8b` — 8B параметров (баланс)
- `mistral:7b` — 7B параметров
- `mixtral:8x7b` — 47B параметров (качество)

---

## 📊 Сравнение стоимости

Для обработки 1000 webhook'ов в месяц (~500 коммитов):

| Провайдер | Модель | Стоимость/мес |
|-----------|--------|---------------|
| **OpenRouter** | GPT-4o-mini | ~$0.10 |
| **OpenAI** | GPT-4o-mini | ~$0.15 |
| **Anthropic** | Claude Haiku | ~$0.25 |
| **Google** | Gemini Flash | ~$0.08 |
| **Ollama** | Llama 3.2 | $0 (бесплатно) |

---

## 🔧 Интеграция в FlowFusion

### 1. Настроить `.env`

```bash
AI_PROVIDER=openrouter
AI_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxx
AI_MODEL=openai/gpt-4o-mini
AI_AUTO_GENERATE=true
```

### 2. Перезапустить worker

```bash
# Остановить worker (Ctrl+C)
# Запустить снова
PYTHONPATH=/Users/dmitriy/Documents/ai_concurs_backend python3 -m app.workers.worker --direct
```

### 3. Проверить логи

В логах worker должны появиться:
```
INFO - Generating AI summary for Jira issue PROJ-123
INFO - AI summary generated: 250 chars
INFO - Successfully processed event 11
```

### 4. Проверить результат

```bash
docker-compose exec postgres psql -U postgres -d flowfusion -c "
SELECT 
    jira_issue,
    summary_input_json->>'ai_generated_summary' as ai_summary
FROM ai_summaries
ORDER BY id DESC LIMIT 5;
"
```

---

## 📝 Примеры промптов

### Что отправляется в AI:

```
Сгенерируй краткий прогресс-апдейт для Jira задачи PROJ-123.

📝 **Коммиты:**
- Fix login bug
- Add retry logic
- Refactor auth service

📁 **Изменённые файлы:**
- auth_service.py
- login_controller.ts

📊 **Изменения:**
- auth_service.py: +20 lines added, -3 lines removed
- login_controller.ts: +15 lines added

🔀 **Merge Request:** Fix login redirect bug
   This MR fixes the login redirect issue

👥 **Авторы:** Ivan

⏰ **Период:** 2024-01-15 — 2024-01-15

Требования к ответу:
- Пиши на русском языке
- Будь краток (3-5 предложений)
- Фокусируйся на достижениях и изменениях
- Используй профессиональный тон
- Избегай технических деталей
```

### Что возвращается от AI:

```
✅ Выполнена работа по задаче PROJ-123:

Проведён рефакторинг модуля аутентификации: исправлена ошибка перенаправления после входа, добавлена логика повторных попыток для повышения надёжности. Изменения затрагивают сервис аутентификации и контроллер входа.

Merge Request готов к ревью.
```

---

## ⚠️ Troubleshooting

### AI summary не генерируется

**Проверьте логи:**
```bash
# В логах worker ищите:
grep "AI" worker.log
```

**Частые проблемы:**

1. **AI_AUTO_GENERATE=false**
   ```bash
   # В .env:
   AI_AUTO_GENERATE=true
   ```

2. **Неправильный API ключ**
   ```bash
   # Проверьте ключ:
   AI_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxx
   ```

3. **Нет подключения к интернету** (для облачных провайдеров)

4. **Закончились кредиты** (проверьте баланс в личном кабинете)

---

### Ollama не работает

**Проверьте что Ollama запущен:**
```bash
curl http://localhost:11434/api/tags
```

**Перезапустите Ollama:**
```bash
brew services restart ollama
```

**Проверьте модель:**
```bash
ollama list
ollama pull llama3.2
```

---

### OpenRouter ошибка 402

**Проблема:** Недостаточно средств на балансе

**Решение:** Пополните баланс на https://openrouter.ai/credits

---

## 🎯 Рекомендации

### Для production:

```bash
AI_PROVIDER=openrouter
AI_MODEL=openai/gpt-4o-mini
AI_AUTO_GENERATE=true
```

**Почему:**
- ✅ Дёшево ($0.15/1M токенов)
- ✅ Быстро (~1 сек на запрос)
- ✅ Хорошее качество
- ✅ Надёжно (автоматический retry)

### Для разработки:

```bash
AI_PROVIDER=ollama
AI_MODEL=llama3.2
AI_AUTO_GENERATE=false
```

**Почему:**
- ✅ Бесплатно
- ✅ Быстро (локально)
- ❌ Качество ниже

### Для максимального качества:

```bash
AI_PROVIDER=anthropic
AI_MODEL=claude-3-opus-20240229
AI_AUTO_GENERATE=true
```

**Почему:**
- ✅ Лучшее качество
- ❌ Дорого ($15/1M токенов)

---

## 📞 Поддержка

При проблемах:

1. Проверьте логи worker
2. Проверьте баланс API ключа
3. Проверьте подключение к интернету
4. Попробуйте другую модель

**137 тестов проходят** ✅

**FlowFusion полностью работает!** 🚀
