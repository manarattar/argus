'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  Bar,
  Callout,
  Card,
  CardHeader,
  ErrorState,
  Metric,
  MetricGrid,
  SectionLabel,
  Table,
  Td,
  Th,
} from '@/components/ui/primitives';
import { ApiError, computeValueCase } from '@/lib/api';
import { formatCompactCurrency, formatCurrency, formatNumber, titleCase } from '@/lib/format';
import type { ValueCaseResult } from '@/lib/types';

interface Sensitivity {
  variable: string;
  base_value: number;
  series: { value: number; annual_net_value: number; break_even_months: number | null }[];
}

/** Which assumptions get a slider, and how they are rendered. */
const FIELDS: {
  key: string;
  label: string;
  min: number;
  max: number;
  step: number;
  format: 'number' | 'currency' | 'hours' | 'percent';
}[] = [
  { key: 'cases_per_month', label: 'Cases per month', min: 10, max: 500, step: 5, format: 'number' },
  { key: 'manual_hours_per_case', label: 'Manual hours per case', min: 1, max: 20, step: 0.5, format: 'hours' },
  { key: 'assisted_hours_per_case', label: 'AI-assisted hours per case', min: 0.5, max: 20, step: 0.5, format: 'hours' },
  { key: 'review_hours_per_case', label: 'Human review hours per case', min: 0, max: 8, step: 0.1, format: 'hours' },
  { key: 'analyst_cost_per_hour', label: 'Analyst cost per hour', min: 20, max: 250, step: 5, format: 'currency' },
  { key: 'ai_cost_per_case', label: 'AI cost per case', min: 0, max: 10, step: 0.01, format: 'currency' },
  { key: 'adoption_rate', label: 'Adoption rate', min: 0, max: 1, step: 0.05, format: 'percent' },
  { key: 'implementation_cost', label: 'Implementation cost', min: 0, max: 1_000_000, step: 10_000, format: 'currency' },
  { key: 'annual_run_cost', label: 'Annual run cost', min: 0, max: 500_000, step: 5_000, format: 'currency' },
];

const SENSITIVITY_OPTIONS = [
  'assisted_hours_per_case',
  'adoption_rate',
  'analyst_cost_per_hour',
  'cases_per_month',
  'ai_cost_per_case',
];

/**
 * The business case.
 *
 * Every input is an assumption the reader can change, and the model is
 * conservative in three deliberate ways: the saving applies to preparation time
 * only, saved hours are expressed as released capacity rather than cost taken
 * out, and the benefit is scaled by an adoption rate. A business case that only
 * works when read optimistically is not a business case.
 */
export function ValueCase({
  defaults,
  notes,
  disclaimer,
}: {
  defaults: Record<string, number>;
  notes: Record<string, string>;
  disclaimer: string;
}) {
  const [assumptions, setAssumptions] = useState<Record<string, number>>(defaults);
  const [variable, setVariable] = useState('assisted_hours_per_case');
  const [result, setResult] = useState<ValueCaseResult | null>(null);
  const [sensitivity, setSensitivity] = useState<Sensitivity | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const compute = useCallback(
    async (values: Record<string, number>, sensitivityVariable: string) => {
      setBusy(true);
      setError(null);
      try {
        const response = await computeValueCase({
          ...values,
          sensitivity_variable: sensitivityVariable,
        });
        setResult(response.result);
        setSensitivity(response.sensitivity);
      } catch (exc) {
        setError(
          exc instanceof ApiError ? exc.message : 'The model could not be computed.',
        );
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  // Debounced so dragging a slider does not fire a request per pixel.
  useEffect(() => {
    const timer = window.setTimeout(() => void compute(assumptions, variable), 220);
    return () => window.clearTimeout(timer);
  }, [assumptions, variable, compute]);

  const invalid =
    (assumptions.assisted_hours_per_case ?? 0) > (assumptions.manual_hours_per_case ?? 0);

  return (
    <div className="grid gap-5 xl:grid-cols-3">
      <div className="space-y-5 xl:col-span-2">
        <Callout tone="warn" title="Illustrative model">
          {disclaimer}
        </Callout>

        {error ? <ErrorState title="Could not compute" detail={error} /> : null}

        {invalid ? (
          <ErrorState
            title="Assumptions are inconsistent"
            detail="AI-assisted hours per case cannot exceed manual hours per case. Adjust one of them."
          />
        ) : null}

        {result ? (
          <>
            <Card>
              <CardHeader
                title="Outcome"
                description="Saved hours are expressed as analyst capacity released, not as cost removed. Nobody leaves a team because a tool got faster."
              />
              <div className="mt-5">
                <MetricGrid columns={4}>
                  <Metric
                    label="Hours saved / month"
                    value={formatNumber(result.monthly_hours_saved, 0)}
                    footnote={`${result.hours_saved_per_case}h per adopted case`}
                  />
                  <Metric
                    label="Capacity released"
                    value={formatCompactCurrency(result.monthly_capacity_value)}
                    footnote="per month, at analyst cost"
                  />
                  <Metric
                    label="Net monthly value"
                    value={formatCompactCurrency(result.monthly_net_value)}
                    footnote="after AI and run cost"
                    tone={result.monthly_net_value < 0 ? 'alert' : 'default'}
                  />
                  <Metric
                    label="Break-even"
                    value={
                      result.break_even_months !== null
                        ? `${result.break_even_months} mo`
                        : 'never'
                    }
                    footnote="on implementation cost"
                    tone={result.break_even_months === null ? 'alert' : 'default'}
                  />
                </MetricGrid>
              </div>

              <div className="mt-6 grid gap-5 sm:grid-cols-2">
                <div>
                  <SectionLabel>Effort per month</SectionLabel>
                  <EffortBar
                    label="Manual today"
                    hours={result.monthly_manual_hours}
                    max={result.monthly_manual_hours}
                    tone="muted"
                  />
                  <EffortBar
                    label="With ARGUS"
                    hours={result.monthly_assisted_hours}
                    max={result.monthly_manual_hours}
                    tone="accent"
                  />
                  <p className="mt-2 text-2xs leading-relaxed text-ink-subtle">
                    {formatNumber(result.effective_cases, 0)} of{' '}
                    {formatNumber(assumptions.cases_per_month ?? 0, 0)} cases are assumed to run
                    through the tool at the current adoption rate.
                  </p>
                </div>
                <div>
                  <SectionLabel>Annualised</SectionLabel>
                  <dl className="space-y-2 text-xs">
                    <Line
                      label="Capacity value"
                      value={formatCurrency(result.monthly_capacity_value * 12, 0)}
                    />
                    <Line
                      label="AI cost"
                      value={`(${formatCurrency(result.monthly_ai_cost * 12, 0)})`}
                    />
                    <Line
                      label="Run cost"
                      value={`(${formatCurrency(result.monthly_run_cost * 12, 0)})`}
                    />
                    <Line
                      label="Net annual value"
                      value={formatCurrency(result.annual_net_value, 0)}
                      emphasis
                    />
                  </dl>
                  <p className="mt-3 text-2xs leading-relaxed text-ink-subtle">
                    Equivalent to roughly{' '}
                    <span className="font-medium text-ink">
                      {formatNumber(result.additional_cases_capacity, 0)}
                    </span>{' '}
                    additional reviews per month from the same team.
                  </p>
                </div>
              </div>
            </Card>

            {sensitivity ? (
              <Card>
                <CardHeader
                  title="Sensitivity"
                  description="Which assumption the conclusion actually depends on. A case that survives only one set of inputs is not a case."
                  actions={
                    <select
                      value={variable}
                      onChange={(event) => setVariable(event.target.value)}
                      aria-label="Sensitivity variable"
                      className="rounded border border-line bg-surface px-2 py-1 text-2xs text-ink"
                    >
                      {SENSITIVITY_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {titleCase(option)}
                        </option>
                      ))}
                    </select>
                  }
                />
                <div className="mt-4">
                  <SensitivityChart sensitivity={sensitivity} />
                </div>
                <div className="mt-4">
                  <Table>
                    <thead>
                      <tr>
                        <Th>{titleCase(sensitivity.variable)}</Th>
                        <Th align="right">Annual net value</Th>
                        <Th align="right">Break-even</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {sensitivity.series.map((point) => (
                        <tr key={point.value}>
                          <Td
                            className={
                              Math.abs(point.value - sensitivity.base_value) < 1e-6
                                ? 'font-semibold text-accent'
                                : undefined
                            }
                          >
                            {point.value}
                          </Td>
                          <Td
                            align="right"
                            className={point.annual_net_value < 0 ? 'text-high' : undefined}
                          >
                            {formatCompactCurrency(point.annual_net_value)}
                          </Td>
                          <Td align="right">
                            {point.break_even_months !== null
                              ? `${point.break_even_months} mo`
                              : 'never'}
                          </Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
              </Card>
            ) : null}
          </>
        ) : (
          <Card>
            <p className="text-xs text-ink-muted">Computing…</p>
          </Card>
        )}
      </div>

      <Card className="h-fit">
        <CardHeader
          title="Assumptions"
          description="Every figure below is editable. None is measured from a production deployment."
        />
        <div className="mt-4 space-y-4">
          {FIELDS.map((field) => (
            <div key={field.key}>
              <div className="flex items-baseline justify-between">
                <label htmlFor={field.key} className="text-2xs font-medium text-ink">
                  {field.label}
                </label>
                <span className="tabular text-xs font-semibold text-ink">
                  {renderValue(assumptions[field.key] ?? 0, field.format)}
                </span>
              </div>
              <input
                id={field.key}
                type="range"
                min={field.min}
                max={field.max}
                step={field.step}
                value={assumptions[field.key] ?? 0}
                onChange={(event) =>
                  setAssumptions((current) => ({
                    ...current,
                    [field.key]: Number(event.target.value),
                  }))
                }
                className="mt-1.5 w-full accent-[rgb(var(--accent))]"
              />
              {notes[field.key] ? (
                <p className="mt-1 text-2xs leading-relaxed text-ink-subtle">
                  {notes[field.key]}
                </p>
              ) : null}
            </div>
          ))}
        </div>
        <button
          onClick={() => setAssumptions(defaults)}
          className="mt-5 w-full rounded border border-line px-3 py-2 text-2xs text-ink-muted hover:bg-raised hover:text-ink"
        >
          Reset to defaults
        </button>
        {busy ? <p className="mt-2 text-center text-2xs text-ink-subtle">Recomputing…</p> : null}
      </Card>
    </div>
  );
}

function EffortBar({
  label,
  hours,
  max,
  tone,
}: {
  label: string;
  hours: number;
  max: number;
  tone: 'muted' | 'accent';
}) {
  return (
    <div className="mb-3">
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-ink-muted">{label}</span>
        <span className="tabular font-medium text-ink">{formatNumber(hours, 0)}h</span>
      </div>
      <Bar value={hours} max={max} tone={tone} className="mt-1" />
    </div>
  );
}

function Line({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between border-b border-line pb-1.5 last:border-0">
      <dt className="text-ink-muted">{label}</dt>
      <dd className={`tabular font-medium ${emphasis ? 'text-ink' : 'text-ink-muted'}`}>
        {value}
      </dd>
    </div>
  );
}

/**
 * Sensitivity chart, drawn as inline SVG.
 *
 * A charting library would be more code and more bundle for one small line
 * chart whose only requirements are a zero line and a marked base case.
 */
function SensitivityChart({ sensitivity }: { sensitivity: Sensitivity }) {
  const { points, zeroY, width, height } = useMemo(() => {
    const w = 640;
    const h = 180;
    const padding = { top: 12, right: 12, bottom: 24, left: 56 };
    const series = sensitivity.series;
    if (series.length === 0) {
      return { points: '', zeroY: 0, width: w, height: h };
    }

    const values = series.map((p) => p.annual_net_value);
    const min = Math.min(0, ...values);
    const max = Math.max(0, ...values);
    const range = max - min || 1;

    const x = (index: number) =>
      padding.left +
      (index / Math.max(series.length - 1, 1)) * (w - padding.left - padding.right);
    const y = (value: number) =>
      padding.top + (1 - (value - min) / range) * (h - padding.top - padding.bottom);

    return {
      points: series.map((p, index) => `${x(index)},${y(p.annual_net_value)}`).join(' '),
      zeroY: y(0),
      width: w,
      height: h,
    };
  }, [sensitivity]);

  if (!points) {
    return <p className="text-xs text-ink-muted">No valid points for this variable.</p>;
  }

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label="Sensitivity">
      <line
        x1={56}
        y1={zeroY}
        x2={width - 12}
        y2={zeroY}
        className="stroke-line-strong"
        strokeDasharray="3 3"
      />
      <text x={50} y={zeroY + 3} textAnchor="end" className="fill-ink-subtle text-[9px]">
        break even
      </text>
      <polyline points={points} fill="none" className="stroke-accent" strokeWidth={2} />
      {sensitivity.series.map((point, index) => {
        const [x, y] = (points.split(' ')[index] ?? '0,0').split(',').map(Number);
        const isBase = Math.abs(point.value - sensitivity.base_value) < 1e-6;
        return (
          <circle
            key={point.value}
            cx={x}
            cy={y}
            r={isBase ? 4.5 : 2.5}
            className={isBase ? 'fill-accent stroke-surface' : 'fill-accent'}
            strokeWidth={isBase ? 2 : 0}
          >
            <title>{`${point.value} → ${formatCompactCurrency(point.annual_net_value)} / year`}</title>
          </circle>
        );
      })}
    </svg>
  );
}

function renderValue(value: number, format: string): string {
  if (format === 'currency') {
    return value >= 1000 ? formatCompactCurrency(value) : formatCurrency(value, 2);
  }
  if (format === 'hours') return `${value}h`;
  if (format === 'percent') return `${Math.round(value * 100)}%`;
  return formatNumber(value, 0);
}
