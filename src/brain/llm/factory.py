"""LLM client factory - the single entry point for building clients."""

import os

from brain.llm.client import BaseLLMClient
from brain.llm.config import LLMConfig, LLMModelError, LLMProvider
from brain.llm.direct_client import LlamaCppDirectClient

DEFAULT_PROVIDER = "llama_cpp"
DEFAULT_MODEL_NAME = "codellama:7b"


def create_llm_client(config: LLMConfig) -> BaseLLMClient:
    """Create the client selected by ``config.provider``.

    ``LlamaCppDirectClient`` is the primary implementation; the Ollama
    client is only kept as an optional fallback.
    """
    if config.provider == LLMProvider.LLAMA_CPP:
        return LlamaCppDirectClient(config)
    if config.provider == LLMProvider.OLLAMA:
        from brain.llm.ollama_client import OllamaClient

        return OllamaClient(config)
    raise LLMModelError(f"Unsupported provider: {config.provider}")


def create_from_env() -> BaseLLMClient:
    """Create a client from ``BRAIN_LLM_*`` environment variables."""
    provider_name = os.getenv("BRAIN_LLM_PROVIDER", DEFAULT_PROVIDER)
    try:
        provider = LLMProvider(provider_name)
    except ValueError as exc:
        raise LLMModelError(
            f"Unsupported BRAIN_LLM_PROVIDER: {provider_name!r}"
        ) from exc

    config = LLMConfig(
        provider=provider,
        model_path=os.getenv("BRAIN_LLM_MODEL_PATH"),
        model_name=os.getenv("BRAIN_LLM_MODEL", DEFAULT_MODEL_NAME),
        n_ctx=int(os.getenv("BRAIN_LLM_N_CTX", "8192")),
        n_gpu_layers=int(os.getenv("BRAIN_LLM_N_GPU_LAYERS", "0")),
        n_threads=int(os.getenv("BRAIN_LLM_N_THREADS", "4")),
        temperature=float(os.getenv("BRAIN_LLM_TEMPERATURE", "0.1")),
        max_tokens=int(os.getenv("BRAIN_LLM_MAX_TOKENS", "4096")),
    )
    return create_llm_client(config)
