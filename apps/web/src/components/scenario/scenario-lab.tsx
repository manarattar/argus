'use client';

import clsx from 'clsx';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Bar,
  Badge,
  Callout,
  Card,
  CardHeader,
  ErrorState,
  Mono,
  RiskBadge,
  SectionLabel,
  Table,
  Td,
  Th,
} from '@/components/ui/primitives';
import { ApiError, runScenario } from '@/lib/api';
import { titleCase } from '@/lib/format';
import type { ScenarioResult, ScenarioVariable } from '@/lib/types';

/**
 * Scenario Lab.
 *
 * The honest version of "what if". A scenario changes a declared structured
 * variable, applies explicit policy-threshold rules to the findings that
 * variable actually drives, and recomputes the rating with the same
 * deterministic engine the investigation used.
 *
 * It does not ask a model to imagine a different company, and it does not
 * invent evidence. That makes it a narrower feature than a free-text
 * what-if box, and a defensible one.
 */
export function ScenarioLab({
  investigationId,
  variables,
  note,
}: {
  investigationId: string;
  variables: ScenarioVariable[];
  note: string;
}) {
  const [activeKey, setActiveKey] = useState(variables[0]?.key ?? '');
  const active = variables.find((v) => v.key === activeKey) ?? variables[0];
  const [value, setValue] = useState(active?.current_value ?? 0);
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!active) {
    return (
      <Callout tone="muted">No scenario variables are configured for this domain.</Callout>
    );
  }

  function selectVariable(key: string) {
    const next = variables.find((v) => v.key === key);
    if (!next) return;
    setActiveKey(key);
    setValue(next.current_value);
    setResult(null);
    setError(null);
  }

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(await runScenario(investigationId, active!.key, value));
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'The scenario could not be computed.');
    } finally {
      setBusy(false);
    }
  }

  const changed = Math.abs(value - active.current_value) > 1e-9;

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <div className="space-y-5 lg:col-span-2">
        <Card>
          <CardHeader
            title="Choose a variable"
            description="Only quantities extracted from the case evidence, and governed by a policy threshold, can be varied."
          />
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {variables.map((variable) => (
              <button
                key={variable.key}
                onClick={() => selectVariable(variable.key)}
                className={clsx(
                  'rounded border px-3.5 py-3 text-left transition-colors',
                  variable.key === activeKey
                    ? 'border-accent bg-accent-soft'
                    : 'border-line bg-surface hover:border-line-strong',
                )}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-xs font-medium text-ink">{variable.label}</span>
                  <span className="tabular text-xs font-semibold text-ink">
                    {variable.current_value}
                    <span className="ml-0.5 text-2xs font-normal text-ink-subtle">
                      {variable.unit}
                    </span>
                  </span>
                </div>
                <p className="mt-1 text-2xs leading-relaxed text-ink-muted">
                  {variable.description}
                </p>
                <p className="mt-1.5 flex items-center gap-1.5 text-2xs text-ink-subtle">
                  <Mono>{variable.policy_reference}</Mono>
                  <span>{variable.source}</span>
                </p>
              </button>
            ))}
          </div>
        </Card>

        <Card>
          <CardHeader
            title={active.label}
            description={`Observed value ${active.current_value}${active.unit ? ` ${active.unit}` : ''}, ${active.source}.`}
          />

          <div className="mt-5">
            <div className="flex items-baseline justify-between">
              <label htmlFor="scenario-value" className="text-2xs uppercase tracking-[0.08em] text-ink-subtle">
                Scenario value
              </label>
              <span className="tabular text-lg font-semibold text-ink">
                {value.toFixed(active.step < 1 ? 1 : 0)}
                <span className="ml-1 text-xs font-normal text-ink-subtle">{active.unit}</span>
              </span>
            </div>
            <input
              id="scenario-value"
              type="range"
              min={active.minimum}
              max={active.maximum}
              step={active.step}
              value={value}
              onChange={(event) => setValue(Number(event.target.value))}
              className="mt-3 w-full accent-[rgb(var(--accent))]"
            />
            <div className="mt-1 flex justify-between text-2xs text-ink-subtle">
              <span>
                {active.minimum} {active.unit}
              </span>
              <span className="text-ink-muted">
                observed: {active.current_value} {active.unit}
              </span>
              <span>
                {active.maximum} {active.unit}
              </span>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button variant="primary" onClick={run} loading={busy} disabled={!changed}>
              Run scenario
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setValue(active.current_value);
                setResult(null);
              }}
              disabled={!changed}
            >
              Reset to observed
            </Button>
            <span className="text-2xs text-ink-subtle">
              Affects: {active.affects.map(titleCase).join(', ')}
            </span>
          </div>

          {error ? (
            <div className="mt-4">
              <ErrorState title="Scenario failed" detail={error} />
            </div>
          ) : null}
        </Card>

        {result ? <ScenarioResultCard result={result} /> : null}
      </div>

      <div className="space-y-5">
        <Callout tone="warn" title="This is a simulation">
          {note}
        </Callout>

        <Card>
          <CardHeader title="How a scenario is computed" />
          <ol className="mt-3 space-y-2.5 text-2xs leading-relaxed text-ink-muted">
            <li>
              <span className="font-semibold text-ink">1. Read the observed value.</span> Taken
              from the case evidence where it can be located, and clearly labelled as a default
              where it cannot.
            </li>
            <li>
              <span className="font-semibold text-ink">2. Map to a severity.</span> The policy
              thresholds for that variable decide what severity the scenario value implies.
            </li>
            <li>
              <span className="font-semibold text-ink">3. Shift the affected findings.</span>{' '}
              Only findings in the categories the variable actually drives are adjusted.
            </li>
            <li>
              <span className="font-semibold text-ink">4. Recompute.</span> The same
              deterministic scoring engine runs again, so the comparison is like for like.
            </li>
          </ol>
          <p className="mt-3 border-t border-line pt-3 text-2xs leading-relaxed text-ink-subtle">
            No model call is involved, and no new evidence is created. The result is a
            projection of the existing evidence under a stated assumption.
          </p>
        </Card>
      </div>
    </div>
  );
}

function ScenarioResultCard({ result }: { result: ScenarioResult }) {
  const delta = result.scenario_score - result.original_score;

  return (
    <Card>
      <CardHeader title="Projected outcome" description={result.explanation} />

      <div className="mt-5 grid gap-5 sm:grid-cols-3">
        <div>
          <SectionLabel>Current</SectionLabel>
          <RiskBadge level={result.original_level} score={result.original_score} size="lg" />
          <p className="mt-1.5 text-2xs text-ink-subtle">
            at {result.original_value} observed
          </p>
        </div>
        <div className="flex flex-col justify-center">
          <div className="flex items-center gap-2">
            <div className="h-px flex-1 bg-line" />
            <span
              className={clsx(
                'tabular text-sm font-semibold',
                delta > 0 ? 'text-high' : delta < 0 ? 'text-low' : 'text-ink-subtle',
              )}
            >
              {delta > 0 ? '+' : ''}
              {delta.toFixed(1)}
            </span>
            <div className="h-px flex-1 bg-line" />
          </div>
          <p className="mt-1 text-center text-2xs text-ink-subtle">points</p>
        </div>
        <div>
          <SectionLabel>Scenario</SectionLabel>
          <RiskBadge level={result.scenario_level} score={result.scenario_score} size="lg" />
          <p className="mt-1.5 text-2xs text-ink-subtle">
            at {result.scenario_value} simulated
          </p>
        </div>
      </div>

      <div className="mt-6">
        <SectionLabel>
          Findings affected ({result.changed_findings.length} of{' '}
          {result.changed_findings.length + result.unaffected_count})
        </SectionLabel>
        {result.changed_findings.length === 0 ? (
          <p className="text-2xs text-ink-muted">
            No finding changes at this value. The scenario stays within the same policy
            threshold band, so the rating is unmoved.
          </p>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Finding</Th>
                <Th>Severity</Th>
                <Th>Likelihood</Th>
                <Th>Why</Th>
              </tr>
            </thead>
            <tbody>
              {result.changed_findings.map((finding) => (
                <tr key={finding.risk_id}>
                  <Td>
                    {finding.title}
                    <span className="mt-0.5 block text-2xs text-ink-subtle">
                      {titleCase(finding.category)}
                    </span>
                  </Td>
                  <Td>
                    <ChangeChip
                      from={finding.original_severity}
                      to={finding.scenario_severity}
                    />
                  </Td>
                  <Td>
                    <ChangeChip
                      from={finding.original_likelihood}
                      to={finding.scenario_likelihood}
                    />
                  </Td>
                  <Td className="text-ink-muted">{finding.explanation}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </div>

      <div className="mt-6">
        <SectionLabel>Scenario score factors</SectionLabel>
        <div className="space-y-2.5">
          {result.factors.map((factor) => {
            const max = Math.max(1, ...result.factors.map((f) => Math.abs(f.contribution)));
            return (
              <div key={factor.key}>
                <div className="flex items-baseline justify-between text-2xs">
                  <span className="text-ink-muted">{factor.label}</span>
                  <span className="tabular font-medium text-ink">
                    {factor.contribution > 0 ? '+' : ''}
                    {factor.contribution.toFixed(1)}
                  </span>
                </div>
                <Bar
                  value={factor.contribution}
                  max={max}
                  tone={
                    factor.direction === 'increases'
                      ? 'negative'
                      : factor.direction === 'decreases'
                        ? 'positive'
                        : 'muted'
                  }
                  className="mt-1"
                />
              </div>
            );
          })}
        </div>
      </div>

      <p className="mt-5 border-t border-line pt-3 text-2xs leading-relaxed text-ink-subtle">
        {result.disclaimer}
      </p>
    </Card>
  );
}

function ChangeChip({ from, to }: { from: string; to: string }) {
  if (from === to) {
    return <span className="text-2xs text-ink-subtle">{titleCase(from)}</span>;
  }
  return (
    <span className="flex items-center gap-1.5 text-2xs">
      <span className="text-ink-subtle line-through">{titleCase(from)}</span>
      <span aria-hidden>→</span>
      <Badge tone="accent">{titleCase(to)}</Badge>
    </span>
  );
}
