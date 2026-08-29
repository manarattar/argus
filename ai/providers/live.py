"""Live model backends.

Two implementations of :class:`~ai.providers.base.LLMProvider` covering the
vendors ARGUS supports out of the box. Both normalise vendor-specific errors
into the shared taxonomy so the orchestration graph never branches on an
SDK exception type.

Neither class reads configuration from the environment itself - construction is
the registry's job (:mod:`ai.providers.registry`), which keeps these classes
trivially constructible in tests.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from ai.providers.base import (
    LLMBadResponse,
    LLMProvider,
    LLMRateLimited,
    LLMRequest,
    LLMResponse,
    LLMUnavailable,
    Timer,
    Usage,
    estimate_tokens,
)


def _classify_status(status: int, body: str) -> Exception:
    """Map an HTTP status onto the shared error taxonomy."""
    if status == 429:
        return LLMRateLimited(f"Rate limited by the model backend: {body[:200]}")
    if status in {401, 403}:
        return LLMUnavailable(f"Model backend rejected the request ({status}).")
    if 500 <= status < 600:
        return LLMUnavailable(f"Model backend error {status}: {body[:200]}")
    return LLMBadResponse(f"Unexpected model backend response {status}: {body[:200]}")


class OpenAICompatibleProvider(LLMProvider):
    """Chat-completions backend for OpenAI and any API-compatible endpoint.

    Covers OpenAI itself plus the many gateways that reimplement the same
    surface, which is why the base URL is a constructor argument rather than a
    constant.
    """

    def __init__(
        self,
        *,
        token: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
    ) -> None:
        self.name = "openai-compatible"
        self.model = model
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def complete(self, request: LLMRequest) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
        }
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            with Timer() as timer, httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": "Bearer " + self._token,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise LLMUnavailable(f"Model backend timed out after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"Could not reach the model backend: {exc}") from exc

        if response.status_code != 200:
            raise _classify_status(response.status_code, response.text)

        try:
            body = response.json()
            text = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLMBadResponse(f"Malformed completion payload: {exc}") from exc

        usage_block = body.get("usage") or {}
        usage = Usage(
            input_tokens=usage_block.get("prompt_tokens", estimate_tokens(request.user)),
            output_tokens=usage_block.get("completion_tokens", estimate_tokens(text)),
        )
        return LLMResponse(
            text=text,
            model=body.get("model", self.model),
            usage=usage,
            latency_ms=timer.elapsed_ms,
            backend=self.name,
            metadata={"finish_reason": body["choices"][0].get("finish_reason", "")},
        )


class AnthropicProvider(LLMProvider):
    """Messages-API backend for Claude models.

    Claude has no JSON response mode, so JSON is elicited by prefilling the
    assistant turn with an opening brace - a standard, reliable technique - and
    the brace is restored before parsing.
    """

    def __init__(
        self,
        *,
        token: str,
        model: str = "claude-haiku-4-5",
        base_url: str = "https://api.anthropic.com/v1",
        timeout: float = 120.0,
    ) -> None:
        self.name = "anthropic"
        self.model = model
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def complete(self, request: LLMRequest) -> LLMResponse:
        messages: list[dict[str, str]] = [{"role": "user", "content": request.user}]
        if request.json_mode:
            messages.append({"role": "assistant", "content": "{"})

        payload = {
            "model": self.model,
            "system": request.system,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }

        try:
            with Timer() as timer, httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}/messages",
                    headers={
                        "x-api-key": self._token,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise LLMUnavailable(f"Model backend timed out after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"Could not reach the model backend: {exc}") from exc

        if response.status_code != 200:
            raise _classify_status(response.status_code, response.text)

        try:
            body = response.json()
            text = "".join(block.get("text", "") for block in body.get("content", []))
        except (KeyError, json.JSONDecodeError) as exc:
            raise LLMBadResponse(f"Malformed completion payload: {exc}") from exc

        if request.json_mode and not text.lstrip().startswith("{"):
            text = "{" + text  # restore the prefilled brace

        usage_block = body.get("usage") or {}
        usage = Usage(
            input_tokens=usage_block.get("input_tokens", estimate_tokens(request.user)),
            output_tokens=usage_block.get("output_tokens", estimate_tokens(text)),
        )
        return LLMResponse(
            text=text,
            model=body.get("model", self.model),
            usage=usage,
            latency_ms=timer.elapsed_ms,
            backend=self.name,
            metadata={"stop_reason": body.get("stop_reason", "")},
        )
