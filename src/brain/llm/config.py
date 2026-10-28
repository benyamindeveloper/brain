"""LLM configuration, message/response types and package exceptions."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    LLAMA_CPP = "llama_cpp"  # Primary: direct llama.cpp via llama-cpp-python
    OLLAMA = "ollama"        # Optional: compatibility / fallback only


@dataclass
class LLMConfig:
    """Configuration for an LLM client."""

    provider: LLMProvider = LLMProvider.LLAMA_CPP
    model_path: Optional[str] = None  # Path to a .gguf model file
    model_name: str = ""              # Model identifier

    # llama.cpp parameters
    n_ctx: int = 8192                 # Context window size
    n_gpu_layers: int = 0             # GPU layers (0 = CPU only)
    n_threads: int = 4                # CPU threads
    n_batch: int = 512                # Batch size for prompt processing
    use_mmap: bool = True             # Use mmap for model loading
    use_mlock: bool = False           # Lock model in memory
    verbose: bool = False             # Verbose llama.cpp output

    # Generation parameters
    temperature: float = 0.1
    top_p: float = 0.95
    top_k: int = 40
    max_tokens: int = 4096
    stop_sequences: List[str] = field(
        default_factory=lambda: ["```", "---", "<|end|>"]
    )

    # Chat template
    chat_template: Optional[str] = None  # Jinja2 template for chat formatting

    # Retry logic
    max_retries: int = 3
    retry_delay: float = 1.0

    # Streaming
    stream: bool = False

    def __post_init__(self) -> None:
        """Coerce ``provider`` given as a plain string into an enum member."""
        if not isinstance(self.provider, LLMProvider):
            self.provider = LLMProvider(self.provider)

    def validation_error(self) -> Optional[str]:
        """Return a readable error, or ``None`` when the config is valid."""
        if self.provider == LLMProvider.LLAMA_CPP:
            if not self.model_path:
                return "model_path is required for the llama_cpp provider"
            if not Path(self.model_path).exists():
                return f"Model file not found: {self.model_path}"
        elif self.provider == LLMProvider.OLLAMA:
            if not self.model_name:
                return "model_name is required for the ollama provider"
        else:
            return f"Unsupported provider: {self.provider.value}"
        return None

    def validate(self) -> bool:
        """Return ``True`` when the configuration is valid."""
        return self.validation_error() is None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation of the configuration."""
        return {
            "provider": self.provider.value,
            "model_path": self.model_path,
            "model_name": self.model_name,
            "n_ctx": self.n_ctx,
            "n_gpu_layers": self.n_gpu_layers,
            "n_threads": self.n_threads,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "max_tokens": self.max_tokens,
        }


@dataclass
class LLMMessage:
    """A single message in the conversation."""

    role: str  # system, user or assistant
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Response returned by an LLM client."""

    content: str
    model: str
    provider: str = "llama_cpp"
    tokens_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = "stop"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation of the response."""
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider,
            "tokens_used": self.tokens_used,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "finish_reason": self.finish_reason,
            "metadata": self.metadata,
        }


class LLMClientError(Exception):
    """Base exception for LLM client errors."""


class LLMModelError(LLMClientError):
    """Model missing, invalid or failed to load."""


class LLMGenerationError(LLMClientError):
    """Generation failed."""


class LLMConnectionError(LLMClientError):
    """Connection to the LLM service failed."""


class LLMTimeoutError(LLMClientError):
    """LLM request timed out."""
