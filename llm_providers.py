"""
llm_providers.py
────────────────
Multi-provider LLM abstraction for the adversarial review pipeline.

Supports:
  - Anthropic (Claude): Best reasoning, nuanced decisions
  - OpenAI (GPT-4o): Better function calling, structured JSON output
  - Google (Gemini): Long context, cost efficiency

Each provider implements the same interface, allowing per-agent
model selection based on task requirements.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
    ) -> LLMResponse:
        """
        Send a completion request to the LLM.

        Args:
            system: System prompt
            messages: List of {"role": "user"|"assistant", "content": str}
            max_tokens: Maximum output tokens

        Returns:
            LLMResponse with text and token usage
        """
        pass


class AnthropicProvider(BaseLLMProvider):
    """
    Anthropic Claude provider.

    Best for: Complex reasoning, nuanced analysis, safety-aware responses.
    Models: claude-sonnet-4-20250514, claude-opus-4-5-20251101, claude-3-5-haiku-latest
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        import anthropic
        self.model = model
        self.client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
    ) -> LLMResponse:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )

        return LLMResponse(
            text=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self.model,
            provider="anthropic",
        )


class OpenAIProvider(BaseLLMProvider):
    """
    OpenAI GPT provider.

    Best for: Structured JSON output, function calling, tool use.
    Models: gpt-4o, gpt-4o-mini, gpt-4-turbo
    """

    def __init__(self, model: str = "gpt-4o"):
        from openai import OpenAI
        self.model = model
        self.client = OpenAI()  # Uses OPENAI_API_KEY env var

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
    ) -> LLMResponse:
        # OpenAI format: system message is first message with role "system"
        openai_messages = [{"role": "system", "content": system}]
        openai_messages.extend(messages)

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=openai_messages,
        )

        return LLMResponse(
            text=response.choices[0].message.content,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            model=self.model,
            provider="openai",
        )


class GeminiProvider(BaseLLMProvider):
    """
    Google Gemini provider.

    Best for: Long context (1M+ tokens), cost efficiency, speed.
    Models: gemini-2.0-flash, gemini-2.5-pro
    """

    def __init__(self, model: str = "gemini-2.0-flash"):
        from google import genai
        self.model = model
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")
        self.client = genai.Client(api_key=api_key)

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
    ) -> LLMResponse:
        # Build conversation with system instruction
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config={
                "system_instruction": system,
                "max_output_tokens": max_tokens,
            },
        )

        # Extract token usage from response
        usage = response.usage_metadata
        return LLMResponse(
            text=response.text,
            input_tokens=usage.prompt_token_count if usage else 0,
            output_tokens=usage.candidates_token_count if usage else 0,
            model=self.model,
            provider="gemini",
        )


# ─── Provider Factory ────────────────────────────────────────────────────────

_PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}


def get_provider(provider_name: str, model: Optional[str] = None) -> BaseLLMProvider:
    """
    Factory function to get the appropriate LLM provider.

    Args:
        provider_name: One of "anthropic", "openai", "gemini"
        model: Optional model override. If not specified, uses provider default.

    Returns:
        Configured LLM provider instance

    Raises:
        ValueError: If provider_name is not recognized
    """
    provider_name = provider_name.lower()

    if provider_name not in _PROVIDERS:
        raise ValueError(
            f"Unknown provider: {provider_name}. "
            f"Available: {list(_PROVIDERS.keys())}"
        )

    provider_class = _PROVIDERS[provider_name]

    if model:
        return provider_class(model=model)
    return provider_class()


def check_api_keys() -> dict[str, bool]:
    """
    Check which API keys are configured.

    Returns:
        Dict mapping provider name to whether its API key is set
    """
    return {
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "gemini": bool(os.environ.get("GOOGLE_API_KEY")),
    }
