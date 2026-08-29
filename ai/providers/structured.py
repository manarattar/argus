"""Schema-enforced generation.

Parsing prose out of a model response is the most common source of brittleness
in LLM pipelines, so ARGUS does not do it. Every agent call goes through
:func:`generate_structured`, which:

1. asks for JSON and appends the target schema to the system prompt;
2. extracts the JSON object, tolerating the wrappers models add (code fences,
   a leading sentence);
3. validates against the Pydantic model;
4. on failure, retries with the validation error fed back in, which is far more
   effective than a bare "try again" because it tells the model precisely which
   field it got wrong;
5. after the retry budget, raises :class:`SchemaValidationFailure`.

Step 5 matters as much as the rest. A step that cannot produce valid output
fails visibly and is recorded as a failed step in the trace. It does not return
an empty object that would quietly read downstream as "nothing found".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from ai.providers.base import LLMBadResponse, LLMError, LLMProvider, LLMRequest, LLMResponse

ModelT = TypeVar("ModelT", bound=BaseModel)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

DEFAULT_MAX_ATTEMPTS = 3


class SchemaValidationFailure(LLMError):
    """The backend never produced output matching the required schema."""

    retryable = False

    def __init__(self, model_name: str, attempts: int, last_error: str) -> None:
        super().__init__(
            f"{model_name} could not be produced after {attempts} attempt(s). "
            f"Last validation error: {last_error}"
        )
        self.model_name = model_name
        self.attempts = attempts
        self.last_error = last_error


@dataclass
class StructuredResult(Generic[ModelT]):
    """A validated model plus the accounting for every attempt it took."""

    value: ModelT
    responses: list[LLMResponse] = field(default_factory=list)

    @property
    def attempts(self) -> int:
        return len(self.responses)

    @property
    def total_latency_ms(self) -> int:
        return sum(r.latency_ms for r in self.responses)

    @property
    def total_cost_usd(self) -> float:
        return round(sum(r.cost_usd for r in self.responses), 6)

    @property
    def input_tokens(self) -> int:
        return sum(r.usage.input_tokens for r in self.responses)

    @property
    def output_tokens(self) -> int:
        return sum(r.usage.output_tokens for r in self.responses)

    @property
    def replayed(self) -> bool:
        return bool(self.responses) and all(r.replayed for r in self.responses)

    @property
    def model(self) -> str:
        return self.responses[-1].model if self.responses else "unknown"


def extract_json_object(text: str) -> dict[str, Any]:
    """Pull the JSON object out of a completion.

    Models wrap JSON in code fences or preface it with a sentence often enough
    that recovering from it is worth doing; anything less recoverable than that
    is treated as a bad response.
    """
    candidate = text.strip()

    fenced = _FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()

    if not candidate.startswith("{"):
        start = candidate.find("{")
        if start == -1:
            raise LLMBadResponse("Response contained no JSON object.")
        candidate = candidate[start:]

    # Trim anything after the matching close brace by scanning depth, which is
    # more reliable than a regex when the payload contains braces in strings.
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(candidate):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = candidate[: index + 1]
                break

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMBadResponse(f"Response was not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise LLMBadResponse("Expected a JSON object at the top level.")
    return parsed


def schema_hint(model: type[BaseModel]) -> str:
    """Compact JSON Schema for the prompt.

    Sent verbatim so the model sees the real constraints - enum members, length
    limits, required fields - rather than a prose paraphrase that can drift out
    of step with the code.
    """
    schema = model.model_json_schema()
    return json.dumps(schema, indent=2, ensure_ascii=False)


def generate_structured(
    provider: LLMProvider,
    schema: type[ModelT],
    *,
    system: str,
    user: str,
    purpose: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> StructuredResult[ModelT]:
    """Generate and validate one structured agent output.

    Args:
        provider: Backend to call.
        schema: Pydantic model the output must satisfy.
        system: Role and rules for the agent.
        user: The task payload, containing only trusted, delimited content.
        purpose: Step name, used for recordings, tracing and cost attribution.
        max_attempts: Total attempts including the first.
        max_tokens: Output budget per attempt.
        temperature: Decoding temperature; zero for reproducibility.

    Returns:
        The validated model and the responses it took to get there.

    Raises:
        SchemaValidationFailure: No attempt produced valid output.
        LLMError: The backend failed in a way retrying cannot fix.
    """
    system_with_schema = (
        f"{system}\n\n"
        "## Required output format\n"
        "Reply with a single JSON object and nothing else - no prose, no code "
        "fence. It must validate against this JSON Schema:\n\n"
        f"{schema_hint(schema)}"
    )

    responses: list[LLMResponse] = []
    correction = ""
    last_error = "no attempt made"

    for attempt in range(1, max_attempts + 1):
        request = LLMRequest(
            system=system_with_schema,
            user=user if not correction else f"{user}\n\n{correction}",
            max_tokens=max_tokens,
            temperature=temperature,
            purpose=purpose,
        )
        response = provider.complete(request)
        responses.append(response)

        try:
            payload = extract_json_object(response.text)
            value = schema.model_validate(payload)
        except (LLMBadResponse, ValidationError) as exc:
            last_error = _summarise_error(exc)
            if attempt == max_attempts:
                break
            correction = (
                "## Correction required\n"
                "Your previous reply did not satisfy the schema. Fix exactly "
                "this and return the complete corrected JSON object:\n"
                f"{last_error}"
            )
            continue

        return StructuredResult(value=value, responses=responses)

    raise SchemaValidationFailure(schema.__name__, len(responses), last_error)


def _summarise_error(exc: Exception) -> str:
    """Turn a validation failure into a short, actionable correction note."""
    if isinstance(exc, ValidationError):
        lines = []
        for error in exc.errors()[:6]:
            location = ".".join(str(part) for part in error["loc"]) or "<root>"
            lines.append(f"- {location}: {error['msg']}")
        remaining = len(exc.errors()) - 6
        if remaining > 0:
            lines.append(f"- ...and {remaining} further problem(s)")
        return "\n".join(lines)
    return str(exc)
