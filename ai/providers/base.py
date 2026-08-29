"""Provider-neutral LLM interface.

Every agent in ARGUS talks to this interface and never to a vendor SDK. That
buys three things the enterprise setting actually needs:

* **Substitutability** - the backend is chosen by configuration, so a model
  change is a deployment decision rather than a code change (ADR-006).
* **Uniform accounting** - latency, tokens and cost are captured in one place,
  which is what makes the AI Operations page real rather than decorative.
* **Uniform failure semantics** - vendor errors are normalised into the small
  set of conditions the orchestration graph knows how to handle: retry, fall
  back, or fail the step honestly.

The interface is deliberately narrow. ARGUS needs one call shape - a system
instruction, a user message, and a demand for JSON - so the abstraction stays
thin instead of reinventing a framework.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# Indicative USD per 1M tokens, used for the cost figures on the AI Operations
# and Value Case pages. Every surface that shows a number derived from this
# labels it as an estimate rather than billing truth.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "text-embedding-3-small": (0.02, 0.00),
}
DEFAULT_PRICING = (0.50, 1.50)


class LLMError(RuntimeError):
    """Base class for backend failures the graph is expected to handle."""

    retryable = False


class LLMUnavailable(LLMError):
    """The backend could not be reached, or returned a server-side error."""

    retryable = True


class LLMRateLimited(LLMError):
    """The backend rejected the call for rate or quota reasons."""

    retryable = True


class LLMBadResponse(LLMError):
    """The backend replied, but not with something usable."""

    retryable = True


class LLMNotConfigured(LLMError):
    """No usable configuration or recording for the requested backend."""

    retryable = False


@dataclass(frozen=True)
class Usage:
    """Token accounting for a single call."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def cost_usd(self, model: str) -> float:
        rate_in, rate_out = MODEL_PRICING.get(model, DEFAULT_PRICING)
        return round(
            (self.input_tokens / 1_000_000) * rate_in + (self.output_tokens / 1_000_000) * rate_out,
            6,
        )


@dataclass(frozen=True)
class LLMResponse:
    """A completion plus everything observability needs to record about it."""

    text: str
    model: str
    usage: Usage = field(default_factory=Usage)
    latency_ms: int = 0
    backend: str = "unknown"
    replayed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def cost_usd(self) -> float:
        return 0.0 if self.replayed else self.usage.cost_usd(self.model)


@dataclass(frozen=True)
class LLMRequest:
    """The single call shape every ARGUS agent uses."""

    system: str
    user: str
    max_tokens: int = 4096
    temperature: float = 0.0
    json_mode: bool = True
    # Names the calling step so recordings, traces and cost attribution all key
    # off the same identifier.
    purpose: str = "generic"


class LLMProvider(ABC):
    """A source of completions."""

    name: str = "abstract"
    model: str = "unknown"
    #: True when calls cost money and can fail for network reasons.
    live: bool = True

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Run one completion, or raise an :class:`LLMError` subclass."""

    def describe(self) -> dict[str, Any]:
        return {"backend": self.name, "model": self.model, "live": self.live}


class Timer:
    """Small helper so every backend reports latency the same way."""

    elapsed_ms: int = 0

    def __enter__(self) -> Timer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: object) -> None:
        self.elapsed_ms = int((time.perf_counter() - self._start) * 1000)


def estimate_tokens(text: str) -> int:
    """Rough token count for backends that do not report usage.

    Four characters per token is the usual English approximation. It is only
    used to keep cost estimates populated when a backend omits usage, and the
    UI labels such figures as estimates.
    """
    return max(1, len(text) // 4)
