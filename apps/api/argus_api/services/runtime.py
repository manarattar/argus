"""Runtime wiring: the one place configuration becomes running components.

Both the model backend and the embedding backend are constructed here and
cached for the process. Everything else in the application - routers, services,
agents, the evaluation harness - receives them as arguments, so nothing else
needs to know how they were chosen or whether a key was present.

:func:`runtime_status` is deliberately exposed to the UI. Any surface showing a
number produced by a model also shows whether that model ran live or was
replayed, because a reviewer should never have to guess which they are looking
at.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ai.providers.base import LLMProvider
from ai.providers.registry import ProviderConfig, build_provider, describe_runtime
from ai.retrieval.embeddings import EmbeddingProvider, build_embedding_provider
from argus_api.core.settings import Settings, get_settings


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    return build_provider(
        ProviderConfig(
            backend=settings.model_backend,
            openai_token=settings.openai_api_key,
            openai_base_url=settings.openai_base_url,
            anthropic_token=settings.anthropic_api_key,
            anthropic_base_url=settings.anthropic_base_url,
            model_name=settings.model_name,
            recordings_dir=settings.recordings_dir,
            record=settings.record_llm_calls,
        )
    )


@lru_cache
def get_embedder() -> EmbeddingProvider:
    settings = get_settings()
    return build_embedding_provider(
        provider=settings.embedding_provider,
        credential=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.embedding_model,
    )


def runtime_status(settings: Settings | None = None) -> dict[str, Any]:
    """Everything the UI banner and the AI Operations page need to be honest."""
    settings = settings or get_settings()
    provider = get_llm_provider()
    embedder = get_embedder()
    status = describe_runtime(provider)
    return {
        **status,
        "environment": settings.environment,
        "embedding": {
            "name": embedder.name,
            "description": embedder.description,
            "semantic": embedder.semantic,
            "dimensions": embedder.dimensions,
            "caveat": (
                None
                if embedder.semantic
                else (
                    "Running the local lexical vectoriser. Retrieval matches on term "
                    "overlap rather than meaning; configure an embedding backend for "
                    "semantic search."
                )
            ),
        },
        "database": "postgresql" if not settings.is_sqlite else "sqlite",
    }


def reset_runtime_caches() -> None:
    """Clear cached backends. Used by tests that change configuration."""
    get_llm_provider.cache_clear()
    get_embedder.cache_clear()
