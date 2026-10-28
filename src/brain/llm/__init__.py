"""LLM package - llama.cpp direct integration (primary) + Ollama fallback."""

from brain.llm.client import BaseLLMClient, LLMClientFactory
from brain.llm.config import (
    LLMClientError,
    LLMConfig,
    LLMConnectionError,
    LLMGenerationError,
    LLMMessage,
    LLMModelError,
    LLMProvider,
    LLMResponse,
    LLMTimeoutError,
)
from brain.llm.direct_client import LlamaCppDirectClient
from brain.llm.factory import create_from_env, create_llm_client
from brain.llm.ollama_client import OllamaClient

__all__ = [
    "BaseLLMClient",
    "LLMClientError",
    "LLMClientFactory",
    "LLMConfig",
    "LLMConnectionError",
    "LLMGenerationError",
    "LLMMessage",
    "LLMModelError",
    "LLMProvider",
    "LLMResponse",
    "LLMTimeoutError",
    "LlamaCppDirectClient",
    "OllamaClient",
    "create_from_env",
    "create_llm_client",
]
