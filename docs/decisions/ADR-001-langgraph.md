# ADR-001 — Orchestrate the investigation as a LangGraph state machine

**Status** Accepted · **Date** 2026-08 · **Decides** how agent steps are sequenced

## Context

The investigation runs seven model-backed steps plus a deterministic
consolidation step. The sequencing has properties that are easy to miss when
first sketching it as a linear pipeline:

- It **branches**. If extraction yields fewer than two grounded evidence items,
  running risk analysis produces findings with nothing behind them. The honest
  outcome is "the file does not support an assessment".
- It must **survive partial failure**. A policy step that fails should not
  discard completed extraction and risk analysis.
- It must **stop and resume**. The workflow pauses for human review and
  continues hours later, potentially in a different process.
- It must be **observable**. Analysts and auditors read the step trace; it is a
  product surface, not a debug log.

## Decision

Use **LangGraph** as an explicit, checkpointable state machine. Nodes are the
agents; the state is one serialisable object; routing is conditional edges; the
graph terminates at the human review gate.

The sequence is **deliberately sequential**, including where concurrency is
available.

## Alternatives considered

**A chain of function calls.** Simplest, and adequate until the first
requirement above. Branching becomes nested conditionals, partial failure
becomes try/except scattered through the flow, and pause/resume is not
expressible at all.

**A generic multi-agent framework with autonomous handoff.** Agents deciding
what runs next produces non-deterministic traces, unpredictable cost, and no way
to guarantee that verification runs before scoring. In a regulated workflow the
control flow is a requirement, not something to delegate to a model.

**A job queue with explicit tasks.** Solves durability, but the control flow ends
up encoded in queue routing rules, which is harder to read than a graph and
harder to test.

**A hand-rolled state machine.** Genuinely viable — perhaps 200 lines. Rejected
because checkpointing, interrupt semantics and typed state are exactly what would
need to be rebuilt, and LangGraph is a small, well-understood dependency.

## Why sequential rather than parallel

Policy analysis and challenging depend only on findings and evidence, so they
could run concurrently. They do not, because:

- the saving is a couple of seconds on a run measured in tens;
- the cost is a non-deterministic trace, and the trace is read by users;
- deterministic ordering makes recorded runs comparable.

Determinism won. This is a trade-off, not an oversight, and it would be revisited
if investigation latency became a real constraint.

## Consequences

**Positive.** Branching, partial failure and the human gate are expressed
directly. Every step is independently traceable. The graph is a readable
description of the workflow. Nodes are bound methods, so they are unit-testable
in isolation.

**Negative.** A framework dependency in the orchestration layer. LangGraph
forbids node names that collide with state keys — discovered during integration
testing, which is why the planning node is called `intake` while its trace
identifier remains `plan`.

**Also learned in testing.** LangGraph propagates only keys declared on the state
TypedDict. An early implementation passed the computed score through an
undeclared key, which was silently dropped and left the assessment unrated. The
score is now carried on the runner instance. The integration suite caught this; a
unit test of the node in isolation would not have.
