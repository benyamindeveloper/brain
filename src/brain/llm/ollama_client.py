"""Optional Ollama fallback client (HTTP API).

Kept only for backwards compatibility; ``LlamaCppDirectClient`` is the
primary client for Project Brain. The server address is taken from the
``BRAIN_OLLAMA_HOST`` environment variable (default
``http://localhost:11434``) because ``LLMConfig`` no longer carries
Ollama specific fields.
"""

import json
import logging
import os
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import requests

from brain.llm.client import BaseLLMClient
from brain.llm.config import (
    LLMConfig,
    LLMConnectionError,
    LLMMessage,
    LLMModelError,
    LLMProvider,
    LLMResponse,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_TIMEOUT = 60.0
MODEL_CACHE_TTL = 60.0


class OllamaClient(BaseLLMClient):
    """Fallback client talking to a running Ollama server."""

    def __init__(
        self, config: LLMConfig, base_url: Optional[str] = None
    ) -> None:
        super().__init__(config)
        host = (
            base_url
            or os.getenv("BRAIN_OLLAMA_HOST")
            or DEFAULT_OLLAMA_HOST
        )
        self.base_url = host.rstrip("/")
        self.timeout = float(
            os.getenv("BRAIN_OLLAMA_TIMEOUT", str(DEFAULT_OLLAMA_TIMEOUT))
        )
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self._model_cache: Optional[List[str]] = None
        self._cache_time: float = 0.0

    def _make_request(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        stream: bool = False,
    ) -> requests.Response:
        """POST ``payload`` to the Ollama HTTP API."""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.post(
                url,
                json=payload,
                stream=stream,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout as exc:
            raise LLMTimeoutError(
                f"Ollama request timed out after {self.timeout}s"
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise LLMConnectionError(
                f"Cannot connect to Ollama at {self.base_url}: {exc}"
            ) from exc
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                raise LLMModelError(
                    f"Model not found: {self.config.model_name}"
                ) from exc
            raise LLMModelError(f"Ollama API error: {exc}") from exc

    def is_available(self) -> bool:
        """Check whether the Ollama server is reachable."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/tags", timeout=5
            )
        except requests.exceptions.RequestException:
            return False
        return response.status_code == 200

    def list_models(self) -> List[str]:
        """List the models available on the Ollama server."""
        if self._model_cache and (
            time.time() - self._cache_time < MODEL_CACHE_TTL
        ):
            return self._model_cache

        try:
            response = self.session.get(
                f"{self.base_url}/api/tags", timeout=10
            )
            response.raise_for_status()
            data = response.json()
        except (requests.exceptions.RequestException, ValueError):
            return list(self._model_cache or [])

        models = [
            str(model.get("name", ""))
            for model in data.get("models", [])
            if model.get("name")
        ]
        self._model_cache = models
        self._cache_time = time.time()
        return list(models)

    def pull_model(self, model_name: str) -> bool:
        """Pull a model from the Ollama registry."""
        try:
            response = self.session.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name, "stream": False},
                timeout=300,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException:
            return False
        self._model_cache = None
        return True

    def _options(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Build the Ollama ``options`` block from kwargs/config."""
        return {
            "temperature": kwargs.get("temperature", self.config.temperature),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "top_k": kwargs.get("top_k", self.config.top_k),
            "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            "stop": kwargs.get("stop", self.config.stop_sequences),
        }

    @staticmethod
    def _usage(data: Dict[str, Any]) -> int:
        """Total token count reported by Ollama."""
        return int(data.get("eval_count", 0) or 0) + int(
            data.get("prompt_eval_count", 0) or 0
        )

    @staticmethod
    def _meta(data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract timing metadata from an Ollama response."""
        return {
            "total_duration": data.get("total_duration"),
            "load_duration": data.get("load_duration"),
            "prompt_eval_count": data.get("prompt_eval_count"),
            "eval_count": data.get("eval_count"),
        }

    @staticmethod
    def _messages_to_prompt(messages: List[LLMMessage]) -> str:
        """Convert messages to a single prompt string for Ollama."""
        parts = []
        for msg in messages:
            if msg.role == "system":
                parts.append(f"System: {msg.content}")
            elif msg.role == "user":
                parts.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                parts.append(f"Assistant: {msg.content}")
        return "\n\n".join(parts) + "\n\nAssistant:"

    @staticmethod
    def _messages_to_ollama(
        messages: List[LLMMessage],
    ) -> List[Dict[str, str]]:
        """Convert messages to the Ollama chat format."""
        return [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]

    def generate(
        self, messages: List[LLMMessage], **kwargs: Any
    ) -> LLMResponse:
        """Generate a response from Ollama."""
        payload = {
            "model": self.config.model_name,
            "prompt": self._messages_to_prompt(messages),
            "stream": False,
            "options": self._options(kwargs),
        }
        data = self._make_request("/api/generate", payload).json()
        return LLMResponse(
            content=data.get("response", ""),
            model=self.config.model_name,
            provider=LLMProvider.OLLAMA.value,
            tokens_used=self._usage(data),
            finish_reason=data.get("done_reason", "stop"),
            metadata=self._meta(data),
        )

    async def generate_stream(
        self, messages: List[LLMMessage], **kwargs: Any
    ) -> AsyncIterator[str]:
        """Yield the Ollama response chunk by chunk."""
        payload = {
            "model": self.config.model_name,
            "prompt": self._messages_to_prompt(messages),
            "stream": True,
            "options": self._options(kwargs),
        }
        response = self._make_request("/api/generate", payload, stream=True)
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            try:
                data = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            token = data.get("response")
            if token:
                yield str(token)
            if data.get("done", False):
                break

    def chat(
        self, messages: List[LLMMessage], **kwargs: Any
    ) -> LLMResponse:
        """Chat completion using Ollama's chat API."""
        payload = {
            "model": self.config.model_name,
            "messages": self._messages_to_ollama(messages),
            "stream": False,
            "options": self._options(kwargs),
        }
        data = self._make_request("/api/chat", payload).json()
        message = data.get("message", {}) or {}
        return LLMResponse(
            content=str(message.get("content", "")),
            model=self.config.model_name,
            provider=LLMProvider.OLLAMA.value,
            tokens_used=self._usage(data),
            finish_reason=data.get("done_reason", "stop"),
            metadata=self._meta(data),
        )
