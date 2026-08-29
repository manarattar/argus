'use client';

import clsx from 'clsx';

import { Badge, Card, CardHeader, Mono, Table, Td, Th } from '@/components/ui/primitives';
import { formatCurrency, formatDuration, stepStatusLabels } from '@/lib/format';
import type { InvestigationDetail, InvestigationStep } from '@/lib/types';

/**
 * The execution trace.
 *
 * It records what each step *did* - capability, tool, retrieval counts,
 * duration, tokens, cost - and never the model's private reasoning. An operator
 * needs the process to debug and trust the system; exposing intermediate model
 * reasoning to end users is both a leakage risk and a poor basis for a
 * decision. There is nothing behind these entries that is being withheld: the
 * system does not store chain-of-thought at all.
 */
export function TracePanel({ investigation }: { investigation: InvestigationDetail }) {
  const steps = [...investigation.steps].sort((a, b) => a.ordinal - b.ordinal);
  const totalDuration = steps.reduce((sum, step) => sum + step.duration_ms, 0);

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title="Execution trace"
          description="What each step did, in order. Model chain-of-thought is neither stored nor displayed."
        />
        <ol className="mt-4 space-y-0">
          {steps.map((step, index) => (
            <StepRow
              key={step.step_id}
              step={step}
              last={index === steps.length - 1}
              share={totalDuration ? step.duration_ms / totalDuration : 0}
            />
          ))}
        </ol>
      </Card>

      <Card>
        <CardHeader
          title="Step accounting"
          description="Per-step model usage and estimated cost."
        />
        <div className="mt-4">
          <Table>
            <thead>
              <tr>
                <Th>Step</Th>
                <Th>Prompt version</Th>
                <Th align="right">Attempts</Th>
                <Th align="right">In</Th>
                <Th align="right">Out</Th>
                <Th align="right">Duration</Th>
                <Th align="right">Est. cost</Th>
              </tr>
            </thead>
            <tbody>
              {steps.map((step) => (
                <tr key={step.step_id}>
                  <Td>
                    {step.name}
                    {step.replayed ? (
                      <span className="ml-1.5 text-2xs text-ink-subtle">(replayed)</span>
                    ) : null}
                  </Td>
                  <Td>
                    {step.prompt_reference ? (
                      <Mono>{step.prompt_reference}</Mono>
                    ) : (
                      <span className="text-2xs text-ink-subtle">deterministic</span>
                    )}
                  </Td>
                  <Td align="right" className={step.retries > 0 ? 'text-moderate' : undefined}>
                    {step.attempts || '—'}
                  </Td>
                  <Td align="right">{step.input_tokens || '—'}</Td>
                  <Td align="right">{step.output_tokens || '—'}</Td>
                  <Td align="right">{formatDuration(step.duration_ms)}</Td>
                  <Td align="right">
                    {step.estimated_cost_usd
                      ? formatCurrency(step.estimated_cost_usd, 5)
                      : '—'}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
        <p className="mt-3 text-2xs text-ink-subtle">
          Cost is estimated from a published price table, not from billing. Replayed steps cost
          nothing.
        </p>
      </Card>
    </div>
  );
}

function StepRow({
  step,
  last,
  share,
}: {
  step: InvestigationStep;
  last: boolean;
  share: number;
}) {
  const meta = stepStatusLabels[step.status] ?? { label: step.status, tone: 'muted' as const };
  const dot =
    meta.tone === 'ok'
      ? 'bg-low'
      : meta.tone === 'warn'
        ? 'bg-moderate'
        : meta.tone === 'alert'
          ? 'bg-high'
          : 'bg-line-strong';

  return (
    <li className="flex gap-3.5">
      <div className="flex flex-col items-center">
        <span className={clsx('mt-1.5 h-2 w-2 shrink-0 rounded-full', dot)} />
        {!last ? <span className="w-px flex-1 bg-line" /> : null}
      </div>
      <div className="min-w-0 flex-1 pb-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="tabular text-2xs text-ink-subtle">
            {new Date(step.started_at).toLocaleTimeString('en-GB')}
          </span>
          <span className="text-xs font-semibold text-ink">{step.name}</span>
          <Badge tone={meta.tone}>{meta.label}</Badge>
          {step.retries > 0 ? (
            <Badge tone="warn" title="The schema validator rejected an earlier attempt.">
              {step.retries} retry{step.retries === 1 ? '' : 'ies'}
            </Badge>
          ) : null}
          {step.replayed ? <Badge tone="muted">replayed</Badge> : null}
          <span className="tabular ml-auto text-2xs text-ink-subtle">
            {formatDuration(step.duration_ms)}
          </span>
        </div>

        <p className="mt-1 text-xs leading-relaxed text-ink-muted">
          {step.summary || 'No summary recorded for this step.'}
        </p>

        {share > 0 ? (
          <div className="mt-1.5 h-0.5 w-full overflow-hidden rounded-full bg-raised">
            <div
              className="h-full rounded-full bg-line-strong"
              style={{ width: `${Math.max(share * 100, 1)}%` }}
            />
          </div>
        ) : null}

        {step.error ? (
          <p className="mt-1.5 rounded border border-high/30 bg-high/5 px-2.5 py-1.5 font-mono text-2xs leading-relaxed text-high">
            {step.error}
          </p>
        ) : null}

        {Object.keys(step.detail ?? {}).length > 0 ? (
          <details className="mt-1.5">
            <summary className="cursor-pointer text-2xs text-ink-subtle hover:text-ink">
              Step detail
            </summary>
            <pre className="scroll-slim mt-1.5 max-h-52 overflow-auto rounded bg-raised px-2.5 py-2 font-mono text-2xs text-ink-muted">
{JSON.stringify(step.detail, null, 2)}
            </pre>
          </details>
        ) : null}
      </div>
    </li>
  );
}
