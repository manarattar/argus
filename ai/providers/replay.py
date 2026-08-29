"""Record-and-replay backend: how Demo Mode stays honest.

The problem this solves
-----------------------
A portfolio project has two audiences with incompatible needs. A recruiter
should be able to clone the repository and see the product work in sixty
seconds, with no account and no spend. An engineer should be able to confirm
the agents are real.

Shipping pre-written answers would fail the second audience, and the failure
would be the exact thing this project argues against: a system that presents
invented output as model output.

The approach
------------
:class:`RecordingProvider` wraps a live backend and writes every
request/response pair to disk. :class:`ReplayProvider` serves those recordings
back, keyed by a hash of the exact prompt.

Two properties follow, and they are the whole point:

1. **Replayed text is genuine model output.** It was produced by a real model
   against these exact prompts, and the recording carries the model name,
   token counts and original latency. No text is authored by hand.
2. **Only generation is replayed.** Chunking, retrieval, grounding
   verification, schema validation, cross-reference integrity, scoring and the
   evaluation harness all execute normally in Demo Mode. If a replayed
   completion cites evidence that does not exist, the pipeline rejects it
   exactly as it would live.

A cache miss is never silently papered over. It raises, and the graph turns
that into a clearly-labelled unavailable step, so the UI shows a real error
state rather than substituting content of its own.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ai.providers.base import LLMNotConfigured, LLMProvider, LLMRequest, LLMResponse, Timer, Usage

RECORDING_VERSION = 1


def request_fingerprint(request: LLMRequest) -> str:
    """Stable key for a request.

    Includes the decoding parameters as well as the prompt text: a recording
    made at a different temperature is not a valid substitute.
    """
    material = json.dumps(
        {
            "system": request.system,
            "user": request.user,
            "temperature": request.temperature,
            "json_mode": request.json_mode,
            "max_tokens": request.max_tokens,
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


@dataclass
class Recording:
    """One captured request/response pair."""

    fingerprint: str
    purpose: str
    model: str
    backend: str
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    version: int = RECORDING_VERSION

    def to_response(self) -> LLMResponse:
        return LLMResponse(
            text=self.text,
            model=self.model,
            usage=Usage(input_tokens=self.input_tokens, output_tokens=self.output_tokens),
            latency_ms=self.latency_ms,
            backend=f"replay:{self.backend}",
            replayed=True,
            metadata={"purpose": self.purpose, "fingerprint": self.fingerprint},
        )


class RecordingStore:
    """A directory of recordings, one JSON file per captured call."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._cache: dict[str, Recording] | None = None

    def _load(self) -> dict[str, Recording]:
        if self._cache is not None:
            return self._cache
        cache: dict[str, Recording] = {}
        if self.directory.exists():
            for path in sorted(self.directory.glob("*.json")):
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    cache[raw["fingerprint"]] = Recording(**raw)
                except (json.JSONDecodeError, KeyError, TypeError):
                    # A corrupt recording is skipped rather than crashing the
                    # app; the miss surfaces as an honest unavailable step.
                    continue
        self._cache = cache
        return cache

    def get(self, fingerprint: str) -> Recording | None:
        return self._load().get(fingerprint)

    def put(self, recording: Recording) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{recording.purpose}-{recording.fingerprint}.json"
        path.write_text(
            json.dumps(asdict(recording), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._load()[recording.fingerprint] = recording

    def stats(self) -> dict[str, Any]:
        recordings = self._load()
        by_purpose: dict[str, int] = {}
        for rec in recordings.values():
            by_purpose[rec.purpose] = by_purpose.get(rec.purpose, 0) + 1
        return {
            "count": len(recordings),
            "by_purpose": by_purpose,
            "models": sorted({r.model for r in recordings.values()}),
            "directory": str(self.directory),
        }

    def invalidate(self) -> None:
        self._cache = None


class RecordingProvider(LLMProvider):
    """Delegates to a live backend and captures every exchange."""

    live = True

    def __init__(self, inner: LLMProvider, store: RecordingStore) -> None:
        self.name = f"recording:{inner.name}"
        self.model = inner.model
        self._inner = inner
        self._store = store

    def complete(self, request: LLMRequest) -> LLMResponse:
        response = self._inner.complete(request)
        self._store.put(
            Recording(
                fingerprint=request_fingerprint(request),
                purpose=request.purpose,
                model=response.model,
                backend=self._inner.name,
                text=response.text,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_ms=response.latency_ms,
            )
        )
        return response


class ReplayProvider(LLMProvider):
    """Serves previously recorded completions. Raises on a miss."""

    live = False

    def __init__(self, store: RecordingStore, *, model_hint: str = "recorded") -> None:
        self.name = "replay"
        self.model = model_hint
        self._store = store

    def complete(self, request: LLMRequest) -> LLMResponse:
        with Timer() as timer:
            recording = self._store.get(request_fingerprint(request))
        if recording is None:
            raise LLMNotConfigured(
                f"Demo Mode has no recording for step '{request.purpose}'. "
                "Configure a model backend to run this step live, or refresh "
                "the demo fixtures with: python -m scripts.record_demo"
            )
        response = recording.to_response()
        # Report the replay's own (negligible) lookup time separately so the
        # operations page can distinguish demo timings from live ones.
        return LLMResponse(
            text=response.text,
            model=response.model,
            usage=response.usage,
            latency_ms=recording.latency_ms,
            backend=response.backend,
            replayed=True,
            metadata={**response.metadata, "replay_lookup_ms": timer.elapsed_ms},
        )

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), **self._store.stats()}
