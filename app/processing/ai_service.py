"""AI Service for generating summaries using various LLM providers.

This service provides a unified interface for multiple AI providers:
- OpenAI (GPT-4, GPT-3.5-turbo)
- Anthropic (Claude)
- Google (Gemini)
- OpenRouter (unified API for multiple models)
- Local LLM (Ollama, vLLM)

The service is designed as a placeholder that can be easily configured
to use any of the supported providers.
"""

import json
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
from app.shared.config import get_settings
from app.shared.logging_config import get_logger

logger = get_logger("ai_service")


class AIClient(ABC):
    """Abstract base class for AI providers."""
    
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        """Generate text from prompt."""
        pass


class OpenAIClient(AIClient):
    """OpenAI API client."""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.openai.com/v1"
    
    def generate(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        try:
            import requests
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt or "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 500,
                "temperature": 0.7
            }
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return None


class OpenRouterClient(AIClient):
    """OpenRouter API client (unified API for 100+ models)."""
    
    def __init__(self, api_key: str, model: str = "openai/gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1"
    
    def generate(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        try:
            import requests
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/your-org/flowfusion",
                "X-Title": "FlowFusion"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt or "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 500,
                "temperature": 0.7
            }
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"OpenRouter API error: {e}")
            return None


class AnthropicClient(AIClient):
    """Anthropic Claude API client."""
    
    def __init__(self, api_key: str, model: str = "claude-3-haiku-20240307"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.anthropic.com/v1"
    
    def generate(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        try:
            import requests
            
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"
            }
            
            payload = {
                "model": self.model,
                "max_tokens": 500,
                "system": system_prompt or "You are a helpful assistant.",
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
            
            response = requests.post(
                f"{self.base_url}/messages",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            return result["content"][0]["text"]
            
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return None


class OllamaClient(AIClient):
    """Local Ollama LLM client (free, runs locally)."""

    def __init__(self, model: str = "llama3.2", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self.timeout = 300  # 5 minutes for long responses

    def generate(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        try:
            import requests

            headers = {"Content-Type": "application/json"}

            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "num_predict": 500,  # Reasonable limit
                    "temperature": 0.5  # Less creative, more accurate
                }
            }

            logger.info(f"Sending request to Ollama (timeout: {self.timeout}s)...")
            response = requests.post(
                f"{self.base_url}/api/generate",
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()

            result = response.json()
            response_text = result.get("response", "")
            
            if response_text:
                logger.info(f"Ollama response: {len(response_text)} chars")
            else:
                logger.warning("Ollama returned empty response")
            
            return response_text

        except requests.Timeout:
            logger.error(f"Ollama request timed out after {self.timeout}s")
            return None
        except Exception as e:
            logger.error(f"Ollama API error: {e}")
            return None


class AIService:
    """
    Main AI service that wraps multiple providers.
    
    Usage:
        ai_service = AIService()
        summary = ai_service.generate_summary(summary_input)
    """
    
    def __init__(self):
        settings = get_settings()
        self.settings = settings
        self.client = self._create_client()
        self.system_prompt = self._load_system_prompt()
    
    def _load_system_prompt(self) -> str:
        """
        Load system prompt from PROMPT.md file.
        
        Returns:
            System prompt text
        """
        import os
        
        # Try multiple paths (for Docker and local development)
        possible_paths = [
            "/app/PROMPT.md",  # Docker root
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "PROMPT.md"),  # Relative
            "/Users/dmitriy/Documents/ai_concurs_backend/PROMPT.md",  # Local dev
        ]
        
        for prompt_path in possible_paths:
            try:
                if os.path.exists(prompt_path):
                    with open(prompt_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        
                    # Extract system prompt from markdown
                    import re
                    match = re.search(r'## 🤖 Системный промпт\n\n```\n(.*?)```', content, re.DOTALL)
                    if match:
                        logger.info(f"Loaded system prompt from {prompt_path}")
                        return match.group(1).strip()
            except Exception as e:
                logger.debug(f"Failed to load from {prompt_path}: {e}")
                continue
        
        # Default fallback
        logger.warning("Using default system prompt")
        return """Ты — помощник для генерации профессиональных прогресс-апдейтов для Jira задач.

Твоя задача:
- Создать краткое резюме выполненной работы
- Использовать деловой стиль
- Фокусироваться на результатах, а не процессе
- Избегать излишних технических деталей
- Писать на русском языке

Формат:
- 3-5 предложений
- Начинать с общего описания работы
- Упоминать ключевые изменения
- Завершать общим статусом"""
    
    def _create_client(self) -> Optional[AIClient]:
        """Create AI client based on configuration."""
        provider = self.settings.AI_PROVIDER.lower()
        api_key = self.settings.AI_API_KEY
        model = self.settings.AI_MODEL
        
        if provider == "openai":
            if not api_key:
                logger.warning("OpenAI API key not configured")
                return None
            return OpenAIClient(api_key, model or "gpt-4o-mini")
        
        elif provider == "openrouter":
            if not api_key:
                logger.warning("OpenRouter API key not configured")
                return None
            return OpenRouterClient(api_key, model or "openai/gpt-4o-mini")
        
        elif provider == "anthropic":
            if not api_key:
                logger.warning("Anthropic API key not configured")
                return None
            return AnthropicClient(api_key, model or "claude-3-haiku-20240307")
        
        elif provider == "ollama":
            return OllamaClient(model or "llama3.2", self.settings.OLLAMA_BASE_URL)
        
        elif provider == "google":
            if not api_key:
                logger.warning("Google API key not configured")
                return None
            # Google Gemini client would be implemented here
            logger.warning("Google Gemini provider not yet implemented")
            return None
        
        else:
            logger.warning(f"Unknown AI provider: {provider}")
            return None
    
    def generate_summary(self, summary_input: Dict[str, Any]) -> Optional[str]:
        """
        Generate AI summary from prepared data.
        
        Args:
            summary_input: Dictionary from AISummaryBuilder
            
        Returns:
            AI-generated summary text, or None if generation failed
        """
        if not self.client:
            logger.debug("AI client not configured, skipping AI summary generation")
            return None
        
        prompt = self._format_prompt(summary_input)
        
        logger.info(f"Generating AI summary for Jira issue {summary_input.get('jira_issue', 'Unknown')}")
        
        try:
            summary = self.client.generate(prompt, self.system_prompt)
            
            if summary and len(summary.strip()) > 10:
                logger.info(f"AI summary generated: {len(summary)} chars")
                logger.debug(f"Summary preview: {summary[:200]}...")
                return summary
            else:
                logger.warning(f"AI returned empty or too short summary for {summary_input.get('jira_issue')}")
                return None
                
        except Exception as e:
            logger.error(f"AI generation failed: {e}")
            return None
    
    def _format_prompt(self, summary_input: Dict[str, Any]) -> str:
        """Format summary input as AI prompt."""
        jira_issue = summary_input.get("jira_issue", "Unknown")
        commits = summary_input.get("commit_messages", [])
        files = summary_input.get("changed_files", [])
        diff = summary_input.get("diff_summary", [])
        mr_title = summary_input.get("merge_request_title", "")
        mr_description = summary_input.get("merge_request_description", "")
        authors = summary_input.get("authors", [])
        time_range = summary_input.get("time_range", {})
        
        prompt_parts = [
            f"Сгенерируй краткий прогресс-апдейт для Jira задачи {jira_issue}.",
            "",
            "📝 **Коммиты:**",
        ]
        
        for msg in commits:
            prompt_parts.append(f"- {msg}")
        
        if files:
            prompt_parts.append("")
            prompt_parts.append("📁 **Изменённые файлы:**")
            for f in files[:15]:
                prompt_parts.append(f"- {f}")
        
        if diff:
            prompt_parts.append("")
            prompt_parts.append("📊 **Изменения:**")
            for d in diff[:15]:
                prompt_parts.append(f"- {d}")
        
        if mr_title:
            prompt_parts.append("")
            prompt_parts.append(f"🔀 **Merge Request:** {mr_title}")
            if mr_description:
                prompt_parts.append(f"   {mr_description}")
        
        if authors:
            prompt_parts.append("")
            prompt_parts.append(f"👥 **Авторы:** {', '.join(authors)}")
        
        if time_range.get("start") and time_range.get("end"):
            prompt_parts.append("")
            prompt_parts.append(f"⏰ **Период:** {time_range['start'][:10]} — {time_range['end'][:10]}")
        
        prompt_parts.append("")
        prompt_parts.append("Требования к ответу:")
        prompt_parts.append("- Пиши на русском языке")
        prompt_parts.append("- Будь краток (3-5 предложений)")
        prompt_parts.append("- Фокусируйся на достижениях и изменениях")
        prompt_parts.append("- Используй профессиональный тон")
        prompt_parts.append("- Избегай технических деталей")
        
        return "\n".join(prompt_parts)


# Convenience function for direct use
def generate_ai_summary(summary_input: Dict[str, Any]) -> Optional[str]:
    """
    Generate AI summary from prepared data.
    
    Convenience function that creates AIService and generates summary.
    
    Args:
        summary_input: Dictionary from AISummaryBuilder
        
    Returns:
        AI-generated summary text, or None if generation failed
    """
    service = AIService()
    return service.generate_summary(summary_input)
