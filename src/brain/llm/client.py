"""Base LLM client interface and client factory."""

import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, List

from brain.llm.config import (
    LLMClientError,
    LLMConfig,
    LLMConnectionError,
    LLMMessage,
    LLMModelError,
    LLMResponse,
    LLMTimeoutError,
)


class BaseLLMClient(ABC):
    """Abstract base class shared by every LLM client."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """Raise :class:`LLMModelError` when the configuration is invalid."""
        error = self.config.validation_error()
        if error is not None:
            raise LLMModelError(error)

    @abstractmethod
    def generate(
        self, messages: List[LLMMessage], **kwargs: Any
    ) -> LLMResponse:
        """Generate a response from the LLM."""

    @abstractmethod
    def generate_stream(
        self, messages: List[LLMMessage], **kwargs: Any
    ) -> AsyncIterator[str]:
        """Generate a streaming response from the LLM."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM service is available."""

    @abstractmethod
    def list_models(self) -> List[str]:
        """List the models available to this client."""

    def generate_with_retry(
        self, messages: List[LLMMessage], **kwargs: Any
    ) -> LLMResponse:
        """Generate with retry logic for transient failures."""
        last_error: LLMClientError | None = None
        for attempt in range(self.config.max_retries):
            try:
                return self.generate(messages, **kwargs)
            except (LLMTimeoutError, LLMConnectionError) as exc:
                last_error = exc
            except LLMClientError as exc:
                last_error = exc
                break

            if attempt < self.config.max_retries - 1:
                time.sleep(self.config.retry_delay * (attempt + 1))

        if last_error is not None:
            raise last_error
        raise LLMClientError("Max retries exceeded")


class LLMClientFactory:
    """Factory for creating LLM clients."""

    @staticmethod
    def create(config: LLMConfig) -> BaseLLMClient:
        """Create an LLM client based on ``config.provider``."""
        from brain.llm.factory import create_llm_client

        return create_llm_client(config)

    @staticmethod
    def create_from_env() -> BaseLLMClient:
        """Create a client from environment variables."""
        from brain.llm.factory import create_from_env

        return create_from_env()
