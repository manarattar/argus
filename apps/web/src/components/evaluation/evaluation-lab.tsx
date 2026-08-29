'use client';

import clsx from 'clsx';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Badge,
  Bar,
  Callout,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Metric,
  MetricGrid,
  Mono,
  SectionLabel,
  Table,
  Td,
  Th,
} from '@/components/ui/primitives';
import { ApiError, runEvaluation } from '@/lib/api';
import { formatDateTime, formatDuration, formatPercent, titleCase } from '@/lib/format';
import type { EvalRun } from '@/lib/types';

const STATUS_TONE = {
  passed: 'ok',
  failed: 'alert',
  skipped: 'muted',
  error: 'alert',
} as const;

/**
 * The Evaluation Lab.
 *
 * Two claims are made honestly here and it matters that both are visible:
 *
 * 1. Pass rate is computed over *executed* cases only.
 * 2. Coverage reports what fraction of the suite actually ran.
 *
 * A run that skips every model-dependent case cannot present itself as a
 * perfect score, because the coverage figure sits directly beside the pass
 * rate. Results are never rounded up and failures are shown, not filtered.
 */
export function EvaluationLab({
  initialRun,
  suite,
  emptyMessage,
}: {
  initialRun: EvalRun | null;
  suite: {
    total: number;
    requires_model: number;
    deterministic: number;
    by_category: Record<string, number>;
    cases: {
      id: string;
      category: string;
      description: string;
      requires_model: boolean;
      tags: string[];
    }[];
  } | null;
  emptyMessage?: string;
}) {
  const [run, setRun] = useState<EvalRun | null>(initialRun);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'failed' | 'skipped'>('all');

  async function execute() {
    setBusy(true);
    setError(null);
    try {
      const response = await runEvaluation();
      setRun(response.run);
    } catch (exc) {
      setError(
        exc instanceof ApiError ? exc.message : 'The evaluation suite could not be run.',
      );
    } finally {
      setBusy(false);
    }
  }

  const runButton = (
    <Button variant="primary" size="lg" onClick={execute} loading={busy}>
      {busy ? 'Running suite…' : run ? 'Re-run suite' : 'Run evaluation suite'}
    </Button>
  );

  if (!run) {
    return (
      <div className="space-y-5">
        {error ? <ErrorState title="Evaluation failed" detail={error} /> : null}
        <EmptyState
          title="No evaluation has been run yet"
          description={
            emptyMessage ??
            'Run the suite to measure retrieval, grounding, scoring, escalation and agent behaviour against the reference corpus.'
          }
          action={runButton}
        />
        {suite ? <SuiteDefinition suite={suite} /> : null}
      </div>
    );
  }

  const metrics = run.metrics;
  const filtered = run.results.filter((result) =>
    filter === 'all'
      ? true
      : filter === 'failed'
        ? result.status === 'failed' || result.status === 'error'
        : result.status === 'skipped',
  );

  return (
    <div className="space-y-5">
      {error ? <ErrorState title="Evaluation failed" detail={error} /> : null}

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <MetricGrid columns={4}>
            <Metric
              label="Pass rate"
              value={formatPercent(metrics.pass_rate, 0)}
              footnote={`${metrics.passed} of ${metrics.executed} executed`}
              hint="Computed over executed cases only. Skipped cases are excluded from the numerator and the denominator."
              tone={metrics.pass_rate !== null && metrics.pass_rate < 0.9 ? 'alert' : 'default'}
            />
            <Metric
              label="Suite coverage"
              value={formatPercent(metrics.coverage, 0)}
              footnote={`${metrics.skipped} case(s) skipped`}
              hint="Fraction of the suite that actually ran. Model-dependent cases are skipped when no backend is available."
              tone={metrics.coverage < 1 ? 'alert' : 'default'}
            />
            <Metric
              label="Failures"
              value={metrics.failed + metrics.errored}
              footnote="Shown in full below"
              tone={metrics.failed + metrics.errored > 0 ? 'alert' : 'default'}
            />
            <Metric
              label="Duration"
              value={formatDuration(metrics.duration_ms)}
              footnote={`${metrics.total_cases} cases`}
            />
          </MetricGrid>
          {runButton}
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-line pt-4 text-2xs text-ink-muted">
          <Badge tone={run.demo_mode ? 'warn' : 'ok'}>
            {run.demo_mode ? 'Replayed responses' : 'Live inference'}
          </Badge>
          <span>model: {run.model_name}</span>
          <span>·</span>
          <span>embeddings: {run.embedding_model}</span>
          <span>·</span>
          <span>{formatDateTime(run.created_at)}</span>
        </div>
      </Card>

      {metrics.skipped > 0 ? (
        <Callout tone="warn" title={`${metrics.skipped} cases were skipped, not passed`}>
          Model-dependent cases - structured output, contradiction detection and prompt-injection
          resistance - need a live model backend or recorded fixtures. They are reported as
          skipped so the pass rate above is not inflated by cases that never ran. Configure a
          model key in <Mono>.env</Mono> to execute them.
        </Callout>
      ) : null}

      <Card>
        <CardHeader
          title="Results by category"
          description="Each category tests a different property of the system. Deterministic categories run everywhere; agent categories need a model."
        />
        <div className="mt-4 space-y-3">
          {Object.entries(metrics.by_category)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([category, bucket]) => {
              const executed = bucket.passed + bucket.failed;
              return (
                <div key={category}>
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-xs font-medium text-ink">{titleCase(category)}</span>
                    <span className="tabular text-2xs text-ink-muted">
                      {executed > 0 ? (
                        <>
                          {bucket.passed}/{executed} passed
                          {bucket.skipped > 0 ? ` · ${bucket.skipped} skipped` : ''}
                        </>
                      ) : (
                        `${bucket.skipped} skipped, none executed`
                      )}
                    </span>
                  </div>
                  <Bar
                    value={bucket.pass_rate ?? 0}
                    max={1}
                    tone={
                      bucket.pass_rate === null
                        ? 'muted'
                        : bucket.pass_rate === 1
                          ? 'positive'
                          : 'negative'
                    }
                    className="mt-1.5"
                  />
                </div>
              );
            })}
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Case results"
          description="Every case, including the ones that failed."
          actions={
            <div className="flex gap-1">
              {(['all', 'failed', 'skipped'] as const).map((option) => (
                <button
                  key={option}
                  onClick={() => setFilter(option)}
                  className={clsx(
                    'rounded border px-2 py-1 text-2xs font-medium capitalize transition-colors',
                    filter === option
                      ? 'border-accent bg-accent-soft text-accent'
                      : 'border-line text-ink-muted hover:text-ink',
                  )}
                >
                  {option}
                </button>
              ))}
            </div>
          }
        />
        <div className="mt-4">
          {filtered.length === 0 ? (
            <EmptyState
              title={filter === 'failed' ? 'No failures' : 'Nothing skipped'}
              description={
                filter === 'failed'
                  ? 'Every executed case passed.'
                  : 'Every case in the suite executed.'
              }
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Case</Th>
                  <Th>Category</Th>
                  <Th>Status</Th>
                  <Th>Expected</Th>
                  <Th>Actual</Th>
                  <Th align="right">Score</Th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((result) => (
                  <tr key={result.case_id}>
                    <Td>
                      <Mono>{result.case_id}</Mono>
                      <span className="mt-1 block text-2xs leading-relaxed text-ink-muted">
                        {result.description}
                      </span>
                    </Td>
                    <Td className="whitespace-nowrap text-ink-muted">
                      {titleCase(result.category)}
                    </Td>
                    <Td>
                      <Badge tone={STATUS_TONE[result.status]}>{result.status}</Badge>
                    </Td>
                    <Td className="font-mono text-2xs text-ink-muted">
                      {truncate(result.expected, 90)}
                    </Td>
                    <Td className="text-2xs text-ink-muted">
                      {result.status === 'skipped'
                        ? String(
                            (result.detail as { reason?: string })?.reason ??
                              'Requires a model backend.',
                          )
                        : truncate(result.actual || result.error, 110)}
                    </Td>
                    <Td align="right">
                      {result.status === 'skipped' ? '—' : result.score.toFixed(2)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </div>
      </Card>

      {suite ? <SuiteDefinition suite={suite} /> : null}
    </div>
  );
}

function SuiteDefinition({
  suite,
}: {
  suite: {
    total: number;
    requires_model: number;
    deterministic: number;
    by_category: Record<string, number>;
  };
}) {
  return (
    <Card>
      <CardHeader
        title="What the suite tests"
        description="The split between deterministic and model-dependent cases is what makes the results comparable across environments."
      />
      <div className="mt-4 grid gap-5 md:grid-cols-2">
        <div>
          <SectionLabel>Deterministic ({suite.deterministic} cases)</SectionLabel>
          <p className="text-2xs leading-relaxed text-ink-muted">
            Retrieval ranking, quote grounding (including negative cases that must be rejected),
            the scoring engine, the uncertainty model, escalation rules, the prompt trust
            boundary and citation integrity on the stored investigation. These need no model and
            run identically on any clone.
          </p>
        </div>
        <div>
          <SectionLabel>Model-dependent ({suite.requires_model} cases)</SectionLabel>
          <p className="text-2xs leading-relaxed text-ink-muted">
            Structured-output conformance, contradiction detection by the Challenger, and three
            prompt-injection cases where a document instructs the model to assign a low rating,
            reveal its instructions, or suppress a category. Skipped - never assumed passed -
            when no backend is available.
          </p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-1.5 border-t border-line pt-4">
        {Object.entries(suite.by_category)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([category, count]) => (
            <Badge key={category} tone="muted">
              {titleCase(category)} · {count}
            </Badge>
          ))}
      </div>
      <p className="mt-3 text-2xs text-ink-subtle">
        Reproducible from the command line with <Mono>make eval</Mono>. The dataset lives at{' '}
        <Mono>data/evals/cases.jsonl</Mono>.
      </p>
    </Card>
  );
}

function truncate(text: string, limit: number): string {
  if (!text) return '—';
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}
