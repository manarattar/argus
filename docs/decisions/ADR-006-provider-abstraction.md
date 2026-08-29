# ADR-006 — One model interface, with record and replay

**Status** Accepted · **Date** 2026-08 · **Decides** how models are called

## Context

Three pressures on the same seam.

**Vendor independence.** Model choice changes for reasons that have nothing to do
with the application: pricing, latency, an internal approval, a capability
change. That should be a deployment decision, not a refactor.

**Uniform accounting and failure handling.** Latency, tokens and cost need to be
captured in one place, and vendor errors need normalising into the small set of
conditions the graph knows how to handle.

**Two incompatible audiences.** A recruiter should see the product work in sixty
seconds with no account and no spend. An engineer should be able to verify the
agents are real. Shipping pre-written answers would satisfy the first and fail
the second — and the failure would be exactly what this project argues against.

## Decision

**A single narrow interface.** `LLMProvider.complete(LLMRequest) -> LLMResponse`.
No vendor SDK is imported outside `ai/providers/`. Agents receive a provider and
have no idea which vendor is behind it.

**Errors are normalised** into `LLMUnavailable`, `LLMRateLimited`,
`LLMBadResponse` and `LLMNotConfigured`, each carrying a `retryable` flag. The
graph branches on these, never on an SDK exception type.

**Structured output is enforced centrally.** `ai/providers/structured.py` appends
the JSON Schema, extracts the object, validates it, and on failure retries with
the validation error fed back — which is far more effective than a bare retry
because it tells the model precisely which field it got wrong. After the budget
the step fails visibly.

**Record and replay.** `RecordingProvider` wraps a live backend and captures every
exchange, keyed by a hash of the exact prompt including decoding parameters.
`ReplayProvider` serves those recordings back.

## Why replay is honest

Two properties, and they are the whole point:

1. **Replayed text is genuine model output.** It was produced by a real model
   against these exact prompts, and the recording carries the model name, token
   counts and original latency. No text is authored by hand.
2. **Only generation is replayed.** Chunking, retrieval, grounding verification,
   schema validation, cross-reference integrity, scoring and the entire
   evaluation harness execute normally. A replayed response citing evidence that
   does not exist is rejected by the same controls that would reject it live.

A cache miss **raises**. It never substitutes content of its own; the graph turns
it into a clearly-labelled failed step and the UI shows the real error. The
operating mode is stated permanently in the sidebar, on every investigation and
against every evaluation run.

## Alternatives considered

**LangChain's model abstraction.** Would work. Rejected because ARGUS needs
exactly one call shape, and adopting a large abstraction to use a fraction of it
imports a dependency surface with no corresponding benefit.

**Vendor SDK directly.** Simplest until the second vendor, at which point every
call site changes.

**Hand-written demo fixtures.** Would produce a smoother demo and would be
dishonest. Rejected explicitly.

**Mock provider returning fixed strings.** Fine for tests — and used there, as
`ScriptedProvider`. Not acceptable as a user-facing mode, because it is not model
output.

**Requiring an API key.** Would make the project unexaminable without an account.

## Consequences

**Positive.** Provider change is a configuration change. Cost and latency are
captured once. Failure handling is uniform. The product is fully explorable with
no key, without misrepresenting what is running. Tests use a scripted provider
and exercise the real structured-output path.

**Negative.** Recordings must be refreshed when prompts change, since the
fingerprint includes prompt text — a version bump invalidates the cache. That is
correct behaviour (a stale recording would misrepresent the current prompt) but
it is a maintenance cost, which `make record` exists to reduce.
