import Link from 'next/link';

import {
  Badge,
  Bar,
  Callout,
  Card,
  CardHeader,
  EmptyState,
  Metric,
  MetricGrid,
  PageHeader,
  Table,
  Td,
  Th,
} from '@/components/ui/primitives';
import { getOperations } from '@/lib/api';
import { formatCurrency, formatDuration, formatNumber, formatPercent, titleCase } from '@/lib/format';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'AI Operations' };

export default async function OperationsPage() {
  const data = await getOperations();

  if (!data) {
    return (
      <>
        <PageHeader eyebrow="AI Operations" title="System operations" />
        <EmptyState
          title="The API is not reachable"
          description="Start the backend and reload."
        />
      </>
    );
  }

  const { totals, overrides, grounding, health } = data;
  const maxCategory = Math.max(1, ...data.category_distribution.map((c) => c.count));

  return (
    <>
      <PageHeader
        eyebrow="AI Operations"
        title="System operations"
        description="Throughput, reliability, cost and human-override behaviour, computed from stored execution records."
      />

      <Card className="mb-5">
        <MetricGrid columns={6}>
          <Metric
            label="Investigations"
            value={totals.investigations}
            footnote={`${totals.steps} steps executed`}
          />
          <Metric
            label="Model calls"
            value={totals.llm_calls}
            footnote={`${totals.retries} schema retries`}
          />
          <Metric
            label="Tokens"
            value={formatNumber(totals.input_tokens + totals.output_tokens)}
            footnote={`${formatNumber(totals.input_tokens)} in / ${formatNumber(totals.output_tokens)} out`}
          />
          <Metric
            label="Estimated cost"
            value={formatCurrency(totals.estimated_cost_usd, 4)}
            footnote="From a price table, not billing"
          />
          <Metric
            label="Failed steps"
            value={totals.failed_steps}
            tone={totals.failed_steps > 0 ? 'alert' : 'default'}
            footnote={formatPercent(health.success_rate, 1) + ' success rate'}
          />
          <Metric
            label="Replayed steps"
            value={totals.replayed_steps}
            footnote="Served from recordings"
          />
        </MetricGrid>
      </Card>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Capability performance"
            description="Each reusable capability, with the work it did and what it cost."
          />
          <div className="mt-4">
            {data.by_capability.length === 0 ? (
              <EmptyState
                title="No steps executed yet"
                description="Run an investigation to populate operational metrics."
              />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Capability</Th>
                    <Th align="right">Runs</Th>
                    <Th align="right">Failures</Th>
                    <Th align="right">Retries</Th>
                    <Th align="right">Avg duration</Th>
                    <Th align="right">Tokens</Th>
                    <Th align="right">Est. cost</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_capability.map((row) => (
                    <tr key={row.capability}>
                      <Td className="font-medium">{titleCase(row.capability)}</Td>
                      <Td align="right">{row.executions}</Td>
                      <Td align="right" className={row.failures > 0 ? 'text-high' : undefined}>
                        {row.failures}
                      </Td>
                      <Td align="right" className={row.retries > 0 ? 'text-moderate' : undefined}>
                        {row.retries}
                      </Td>
                      <Td align="right">{formatDuration(row.avg_duration_ms)}</Td>
                      <Td align="right">
                        {formatNumber(row.input_tokens + row.output_tokens)}
                      </Td>
                      <Td align="right">
                        {row.cost_usd ? formatCurrency(row.cost_usd, 5) : '—'}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </div>
          <p className="mt-3 text-2xs leading-relaxed text-ink-subtle">{data.trace_policy}</p>
        </Card>

        <div className="space-y-5">
          <Card>
            <CardHeader
              title="Human override behaviour"
              description="The most honest read on whether the system is useful."
            />
            <dl className="mt-4 space-y-2.5 text-xs">
              <Row label="Findings produced" value={String(overrides.total_findings)} />
              <Row label="Findings adjusted" value={String(overrides.findings_overridden)} />
              <Row
                label="Override rate"
                value={formatPercent(overrides.override_rate, 0)}
                emphasis
              />
              <Row label="Reviews submitted" value={String(overrides.reviews_submitted)} />
              <Row
                label="Reviews changing the rating"
                value={String(overrides.reviews_changing_overall_level)}
              />
            </dl>
            <p className="mt-3 border-t border-line pt-3 text-2xs leading-relaxed text-ink-subtle">
              A rate near zero suggests analysts are accepting output without scrutiny. A very
              high rate suggests the model is not earning its place. Both are failure modes, and
              neither is visible without storing the AI recommendation alongside the human
              decision.
            </p>
          </Card>

          <Card>
            <CardHeader
              title="Grounding control"
              description="How often the anti-hallucination control actually fired."
            />
            <dl className="mt-4 space-y-2.5 text-xs">
              <Row label="Evidence proposed" value={String(grounding.evidence_proposed)} />
              <Row label="Accepted" value={String(grounding.evidence_grounded)} />
              <Row
                label="Rejected"
                value={String(grounding.evidence_rejected)}
                emphasis={grounding.evidence_rejected > 0}
              />
              <Row
                label="Rejection rate"
                value={formatPercent(grounding.rejection_rate, 1)}
              />
              <Row
                label="Mean grounding score"
                value={formatPercent(grounding.mean_grounding_score, 0)}
              />
            </dl>
          </Card>
        </div>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Where findings land"
            description="Distribution of findings across the risk taxonomy."
          />
          <div className="mt-4 space-y-2.5">
            {data.category_distribution.length === 0 ? (
              <p className="text-xs text-ink-muted">No findings recorded yet.</p>
            ) : (
              data.category_distribution.map((row) => (
                <div key={row.category}>
                  <div className="flex items-baseline justify-between text-xs">
                    <span className="text-ink-muted">{titleCase(row.category)}</span>
                    <span className="tabular font-medium text-ink">{row.count}</span>
                  </div>
                  <Bar value={row.count} max={maxCategory} className="mt-1" />
                </div>
              ))
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Latest evaluation"
            description="Measured system quality, not asserted."
          />
          {data.latest_evaluation ? (
            <div className="mt-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="accent">
                  {data.latest_evaluation.passed}/{data.latest_evaluation.total} passed
                </Badge>
                {data.latest_evaluation.failed > 0 ? (
                  <Badge tone="alert">{data.latest_evaluation.failed} failed</Badge>
                ) : null}
                <span className="text-2xs text-ink-subtle">
                  {new Date(data.latest_evaluation.created_at).toLocaleString('en-GB')}
                </span>
              </div>
              <Link
                href="/evaluation"
                className="mt-4 inline-block text-xs text-accent hover:underline"
              >
                Open the Evaluation Lab
              </Link>
            </div>
          ) : (
            <div className="mt-4">
              <Callout tone="muted">
                No evaluation has been run. Run one from the Evaluation Lab, or with{' '}
                <code className="font-mono">make eval</code>.
              </Callout>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

function Row({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between border-b border-line pb-2 last:border-0 last:pb-0">
      <dt className="text-ink-muted">{label}</dt>
      <dd className={`tabular font-medium ${emphasis ? 'text-accent' : 'text-ink'}`}>{value}</dd>
    </div>
  );
}
