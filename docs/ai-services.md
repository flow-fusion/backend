# AI Service Configuration

FlowFusion поддерживает множественные AI-провайдеры для генерации саммари.

## Поддерживаемые провайдеры

| Провайдер | Модели | Стоимость | Качество |
|-----------|--------|-----------|----------|
| **OpenRouter** | 100+ моделей | от $0.10/1M | ⭐⭐⭐⭐⭐ |
| **OpenAI** | GPT-4, GPT-3.5 | $0.15-10/1M | ⭐⭐⭐⭐⭐ |
| **Anthropic** | Claude 3 | $3-15/1M | ⭐⭐⭐⭐⭐ |
| **Google** | Gemini | $0.075-7/1M | ⭐⭐⭐⭐ |
| **Ollama** | Llama, Mistral | Бесплатно | ⭐⭐⭐ |

## Быстрая настройка

### OpenRouter (рекомендуется)

```bash
AI_PROVIDER=openrouter
AI_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxx
AI_MODEL=openai/gpt-4o-mini
AI_AUTO_GENERATE=true
```

**Преимущества:** доступ к 100+ моделям через один API, автоматический fallback.

### OpenAI

```bash
AI_PROVIDER=openai
AI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
AI_MODEL=gpt-4o-mini
AI_AUTO_GENERATE=true
```

### Anthropic

```bash
AI_PROVIDER=anthropic
AI_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx
AI_MODEL=claude-3-haiku-20240307
AI_AUTO_GENERATE=true
```

### Google Gemini

```bash
AI_PROVIDER=google
AI_API_KEY=xxxxxxxxxxxxxxxxxxxx
AI_MODEL=gemini-1.5-flash
AI_AUTO_GENERATE=true
```

### Ollama (локально)

```bash
AI_PROVIDER=ollama
AI_MODEL=llama3.2
AI_AUTO_GENERATE=true
OLLAMA_BASE_URL=http://localhost:11434
```

**Преимущества:** бесплатно, приватность, работает без интернета.  
**Недостатки:** требует ресурсы, качество ниже.

## Проверка работы

После настройки проверьте логи worker:

```bash
docker-compose logs worker | grep "AI"
```

Ожидаемые логи:
```
INFO - Generating AI summary for Jira issue PROJ-123
INFO - AI summary generated: 250 chars
```

## Troubleshooting

**AI summary не генерируется:**
1. Проверьте `AI_AUTO_GENERATE=true`
2. Проверьте API ключ
3. Проверьте подключение к интернету (для облачных провайдеров)

**Ollama не работает:**
```bash
docker-compose exec ollama ollama list
docker-compose exec ollama ollama run llama3.2 "Привет!"
```

## Рекомендации

**Production:** `openai/gpt-4o-mini` через OpenRouter — дёшево ($0.15/1M), быстро, качественно.

**Разработка:** `llama3.2` локально — бесплатно, приватно.

**Максимальное качество:** `claude-3-opus-20240229` — дорого ($15/1M), но лучшее качество.
