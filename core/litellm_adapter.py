"""
LiteLLM Adapter - Universal fallback for 100+ LLM providers

Integrates LiteLLM as a fallback adapter for providers not explicitly supported
in llm_router.py. Provides access to 100+ providers through unified interface.

GOVERNANCE: Part of Priority 1 skill integration
AUTHOR: Claude Code (claude-code)
VERSION: 1.0
CHECKSUM: ΔΣ=42
"""

import logging
from typing import Optional
import litellm

# Suppress LiteLLM's verbose logging
litellm.suppress_debug_info = True
logging.getLogger("LiteLLM").setLevel(logging.WARNING)


def litellm_fallback(provider_name: str, model: str, prompt: str,
                     api_key: Optional[str] = None,
                     api_base: Optional[str] = None,
                     timeout: int = 30) -> Optional[str]:
    """
    Use LiteLLM to call any of 100+ supported providers.

    Args:
        provider_name: Provider name (for logging)
        model: LiteLLM model identifier (e.g., "gpt-4", "claude-3-sonnet", "ollama/llama3")
        prompt: The prompt to send
        api_key: Optional API key (can also use env vars)
        api_base: Optional custom API base URL
        timeout: Request timeout in seconds

    Returns:
        Response text or None on failure
    """
    try:
        # Build kwargs for litellm.completion()
        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "timeout": timeout,
            "num_retries": 2  # LiteLLM built-in retry logic
        }

        if api_key:
            kwargs["api_key"] = api_key
        if api_base:
            kwargs["api_base"] = api_base

        # Call LiteLLM
        response = litellm.completion(**kwargs)

        # Extract response text
        if response and response.choices and len(response.choices) > 0:
            return response.choices[0].message.content
        else:
            logging.warning(f"LiteLLM {provider_name}: Empty response")
            return None

    except Exception as e:
        logging.warning(f"LiteLLM {provider_name} failed: {e}")
        return None


def get_litellm_model_name(provider_name: str, model: str) -> str:
    """
    Map our provider names to LiteLLM model format.

    Args:
        provider_name: Our internal provider name
        model: Our internal model name

    Returns:
        LiteLLM-formatted model string
    """
    # LiteLLM model format: https://docs.litellm.ai/docs/providers

    # Ollama models
    if provider_name.startswith("Ollama"):
        return f"ollama/{model}"

    # Anthropic models
    if "Claude" in provider_name or "Anthropic" in provider_name:
        return model  # Already in correct format (claude-3-sonnet-20240229, etc)

    # OpenAI models
    if "OpenAI" in provider_name or "GPT" in provider_name:
        return model  # Already in correct format (gpt-4, gpt-3.5-turbo, etc)

    # Groq models
    if "Groq" in provider_name:
        return f"groq/{model}"

    # Cerebras models
    if "Cerebras" in provider_name:
        return f"cerebras/{model}"

    # Default: assume model name is correct
    return model
