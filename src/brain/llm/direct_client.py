"""Direct llama.cpp client built on ``llama-cpp-python``.

This is the PRIMARY client for Project Brain: the model runs in-process,
no external server (e.g. Ollama) is required.
"""

import logging
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List

from brain.llm.client import BaseLLMClient
from brain.llm.config import (
    LLMConfig,
    LLMGenerationError,
    LLMMessage,
    LLMModelError,
    LLMProvider,
    LLMResponse,
)

logger = logging.getLogger(__name__)


class LlamaCppDirectClient(BaseLLMClient):
    """In-process llama.cpp client (primary LLM client)."""

    def __init__(self, config: LLMConfig) -> None:
        self._model: Any = None
        self._model_initialized = False
        super().__init__(config)
        self._init_model()

    def _init_model(self) -> None:
        """Load the gguf model described by the configuration."""
        if not self.config.model_path:
            raise LLMModelError("model_path is not configured")

        model_path = Path(self.config.model_path)
        if not model_path.exists():
            raise LLMModelError(f"Model file not found: {model_path}")

        from llama_cpp import Llama

        try:
            logger.info("Loading model from %s", model_path)
            self._model = Llama(
                model_path=str(model_path),
                n_ctx=self.config.n_ctx,
                n_gpu_layers=self.config.n_gpu_layers,
                n_threads=self.config.n_threads,
                n_batch=self.config.n_batch,
                use_mmap=self.config.use_mmap,
                use_mlock=self.config.use_mlock,
                verbose=self.config.verbose,
                chat_format=self.config.chat_template or None,
            )
            self._model_initialized = True
            logger.info("Model loaded: %s", self.config.model_path)
        except Exception as exc:
            logger.error("Failed to load model: %s", exc)
            raise LLMModelError(
                f"Failed to initialize llama.cpp model: {exc}"
            ) from exc

    def is_available(self) -> bool:
        """Return ``True`` when the model is loaded and ready."""
        return self._model_initialized and self._model is not None

    def list_models(self) -> List[str]:
        """Return the loaded model identifier."""
        if self.config.model_name:
            return [self.config.model_name]
        if self.config.model_path:
            return [Path(self.config.model_path).name]
        return []

    def _messages_to_chat(
        self, messages: List[LLMMessage]
    ) -> List[Dict[str, str]]:
        """Convert messages to the llama.cpp chat format."""
        return [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]

    def _generation_kwargs(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Merge call site overrides with the configured defaults."""
        return {
            "temperature": kwargs.get("temperature", self.config.temperature),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "top_k": kwargs.get("top_k", self.config.top_k),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "stop": kwargs.get("stop", self.config.stop_sequences),
        }

    @property
    def model_label(self) -> str:
        """Human readable identifier of the loaded model."""
        if self.config.model_path:
            return Path(self.config.model_path).name
        return self.config.model_name

    def generate(
        self, messages: List[LLMMessage], **kwargs: Any
    ) -> LLMResponse:
        """Generate a response from the model."""
        if not self.is_available():
            raise LLMGenerationError("Model not initialized")

        start_time = time.time()
        chat_messages = self._messages_to_chat(messages)
        params = self._generation_kwargs(kwargs)

        try:
            response = self._model.create_chat_completion(
                messages=chat_messages,
                stream=False,
                **params,
            )
        except Exception as exc:
            logger.error("Generation failed: %s", exc)
            raise LLMGenerationError(f"Generation failed: {exc}") from exc

        choice = response["choices"][0]
        usage = response.get("usage", {}) or {}
        return LLMResponse(
            content=choice["message"]["content"],
            model=self.model_label,
            provider=LLMProvider.LLAMA_CPP.value,
            tokens_used=int(usage.get("total_tokens", 0) or 0),
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            finish_reason=choice.get("finish_reason", "stop"),
            metadata={
                "duration_ms": int((time.time() - start_time) * 1000),
                "model_path": self.config.model_path,
            },
        )

    async def generate_stream(
        self, messages: List[LLMMessage], **kwargs: Any
    ) -> AsyncIterator[str]:
        """Yield the generated answer chunk by chunk."""
        if not self.is_available():
            raise LLMGenerationError("Model not initialized")

        chat_messages = self._messages_to_chat(messages)
        params = self._generation_kwargs(kwargs)

        try:
            stream = self._model.create_chat_completion(
                messages=chat_messages,
                stream=True,
                **params,
            )
            for chunk in stream:
                delta = chunk["choices"][0]["delta"]
                token = delta.get("content")
                if token:
                    yield token
        except Exception as exc:
            logger.error("Stream generation failed: %s", exc)
            raise LLMGenerationError(
                f"Stream generation failed: {exc}"
            ) from exc

    def chat(
        self, messages: List[LLMMessage], **kwargs: Any
    ) -> LLMResponse:
        """Chat completion interface (alias for :meth:`generate`)."""
        return self.generate(messages, **kwargs)

    def close(self) -> None:
        """Release the model resources."""
        if self._model is not None:
            self._model = None
            self._model_initialized = False
            logger.info("Model resources released")

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # pragma: no cover - interpreter shutdown
            pass

    def __enter__(self) -> "LlamaCppDirectClient":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        self.close()
