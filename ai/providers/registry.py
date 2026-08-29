"""Backend selection.

One place decides which model backend the whole application uses, and it
decides from configuration only. Agents receive a :class:`LLMProvider` and have
no idea which vendor is behind it - the property ADR-006 argues for.

Resolution order for ``model_backend="auto"``:

1. an OpenAI-compatible token, if configured;
2. an Anthropic token, if configured;
3. replay from ``data/recordings`` otherwise.

Step 3 is what lets a fresh clone work. It is also why the resolution is
reported to the UI (:func:`describe_runtime`) rather than kept internal: a
reviewer should always be able to see, on screen, whether the numbers in front
of them came from a live model or from a recording.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai.providers.base import LLMProvider
from ai.providers.live import AnthropicProvider, OpenAICompatibleProvider
from ai.providers.replay import RecordingProvider, RecordingStore, ReplayProvider


@dataclass(frozen=True)
class ProviderConfig:
    """The subset of settings the registry needs, decoupled from FastAPI."""

    backend: str = "auto"
    openai_token: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_token: str = ""
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    model_name: str = "gpt-4o-mini"
    recordings_dir: Path = Path("data/recordings")
    record: bool = False


def build_provider(config: ProviderConfig) -> LLMProvider:
    """Construct the model backend the configuration calls for."""
    store = RecordingStore(config.recordings_dir)
    backend = config.backend.lower()

    if backend == "replay":
        return ReplayProvider(store, model_hint=config.model_name)

    live: LLMProvider | None = None
    if backend in {"auto", "openai"} and config.openai_token:
        live = OpenAICompatibleProvider(
            token=config.openai_token,
            model=config.model_name,
            base_url=config.openai_base_url,
        )
    elif backend in {"auto", "anthropic"} and config.anthropic_token:
        live = AnthropicProvider(
            token=config.anthropic_token,
            model=(
                config.model_name if config.model_name.startswith("claude") else "claude-haiku-4-5"
            ),
            base_url=config.anthropic_base_url,
        )

    if live is None:
        # No usable configuration: serve recordings rather than failing at
        # import time, so the product remains explorable.
        return ReplayProvider(store, model_hint=config.model_name)

    return RecordingProvider(live, store) if config.record else live


def describe_runtime(provider: LLMProvider) -> dict[str, Any]:
    """Human-readable summary of what is actually running, for the UI banner."""
    info = provider.describe()
    replaying = not provider.live
    return {
        **info,
        "mode": "demo" if replaying else "live",
        "headline": (
            "Demo Mode - serving recorded model responses"
            if replaying
            else f"Live inference - {info.get('model')}"
        ),
        "explanation": (
            "Retrieval, grounding checks, schema validation, scoring and "
            "evaluation all execute normally. Only text generation is served "
            "from recordings captured against a real model."
            if replaying
            else "Every agent step calls the configured model backend directly."
        ),
    }
