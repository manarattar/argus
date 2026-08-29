import Link from 'next/link';

import { LinkButton } from '@/components/ui/button';
import {
  Badge,
  Callout,
  Card,
  CardHeader,
  EmptyState,
  Metric,
  MetricGrid,
  PageHeader,
  RiskBadge,
  Table,
  Td,
  Th,
} from '@/components/ui/primitives';
import { getDashboard } from '@/lib/api';
import {
  formatCurrency,
  formatDuration,
  formatPercent,
  relativeTime,
  riskClasses,
  RISK_LEVELS,
} from '@/lib/format';

export const dynamic = 'force-dynamic';

export default async function OverviewPage() {
  const data = await getDashboard();

  if (!data) {
    return (
      <>
        <PageHeader
          eyebrow="Overview"
          title="Portfolio status"
          description="Counterparty review activity across the book."
        />
        <EmptyState
          title="The API is not reachable"
          description={
            <>
              Start the backend with <code className="font-mono">make api</code>, then reload.
              If this is a fresh clone, run <code className="font-mono">make seed</code> first.
            </>
          }
        />
      </>
    );
  }

  const hasActivity = data.investigations.total > 0;

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Portfolio status"
        description="AI investigates and recommends. A named analyst decides. Nothing here is a final credit decision."
        actions={<LinkButton href="/cases" variant="primary">Open cases</LinkButton>}
      />

      <Card className="mb-5">
        <MetricGrid columns={6}>
          <Metric
            label="Active cases"
            value={data.cases.active}
            footnote={`${data.cases.total} total`}
            hint="Cases not yet approved or rejected."
          />
          <Metric
            label="Awaiting decision"
            value={data.cases.awaiting_review}
            tone={data.cases.awaiting_review > 0 ? 'alert' : 'default'}
            footnote="Held at the review gate"
            hint="Investigations that completed and are waiting for a human decision."
          />
          <Metric
            label="Avg investigation"
            value={formatDuration(data.average_investigation_ms)}
            footnote="End to end"
            hint="Mean wall-clock duration of a completed investigation."
          />
          <Metric
            label="Override rate"
            value={formatPercent(data.human_override_rate, 0)}
            footnote="Findings analysts changed"
            hint="Share of findings where a human changed the AI recommendation."
          />
          <Metric
            label="Evidence coverage"
            value={formatPercent(data.evidence_coverage, 0)}
            footnote="Expected categories met"
            hint="Mean share of expected evidence categories fully covered."
          />
          <Metric
            label="Model cost"
            value={formatCurrency(data.estimated_cost_usd, 3)}
            footnote="Estimated, all runs"
            hint="Derived from a published price table, not from billing."
          />
        </MetricGrid>
      </Card>

      {!hasActivity ? (
        <Callout tone="accent" title="No investigation has run yet">
          Seed the demonstration case and run the graph with{' '}
          <code className="font-mono">make seed-full</code>, or open the Northstar case and
          start an investigation from there.
        </Callout>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Recent investigations"
            description="Most recent runs, with the rating the scoring engine computed."
            actions={
              <Link href="/cases" className="text-xs text-accent hover:underline">
                All cases
              </Link>
            }
          />
          <div className="mt-4">
            {data.recent.length === 0 ? (
              <EmptyState
                title="Nothing has run yet"
                description="Investigations will appear here once the graph has executed."
              />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Counterparty</Th>
                    <Th>Rating</Th>
                    <Th align="right">Findings</Th>
                    <Th align="right">Evidence</Th>
                    <Th align="right">Duration</Th>
                    <Th>Started</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent.map((run) => (
                    <tr key={run.id} className="group">
                      <Td>
                        <Link
                          href={`/cases/${run.case_id}`}
                          className="font-medium text-ink group-hover:text-accent"
                        >
                          {run.organisation || run.case_id}
                        </Link>
                        <span className="mt-0.5 flex items-center gap-1.5">
                          <span className="text-2xs text-ink-subtle">{run.reference}</span>
                          {run.demo_mode ? (
                            <Badge tone="muted" title="Model responses were replayed from recordings.">
                              replayed
                            </Badge>
                          ) : null}
                          {run.has_errors ? (
                            <Badge tone="alert" title="At least one step failed during this run.">
                              step failed
                            </Badge>
                          ) : null}
                        </span>
                      </Td>
                      <Td>
                        <RiskBadge level={run.overall_level} score={run.overall_score} />
                      </Td>
                      <Td align="right">{run.findings}</Td>
                      <Td align="right">{run.evidence_count}</Td>
                      <Td align="right">{formatDuration(run.duration_ms)}</Td>
                      <Td className="whitespace-nowrap text-ink-muted">
                        {relativeTime(run.started_at)}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </div>
        </Card>

        <div className="space-y-5">
          <Card>
            <CardHeader
              title="Risk distribution"
              description="Provisional ratings across investigations."
            />
            <div className="mt-4 space-y-2.5">
              {RISK_LEVELS.map((level) => {
                const count = data.risk_distribution[level] ?? 0;
                const total = Object.values(data.risk_distribution).reduce((a, b) => a + b, 0);
                const pct = total ? (count / total) * 100 : 0;
                return (
                  <div key={level}>
                    <div className="mb-1 flex items-baseline justify-between text-xs">
                      <span className="capitalize text-ink-muted">{level}</span>
                      <span className="tabular font-medium text-ink">{count}</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-raised">
                      <div
                        className={`h-full rounded-full ${riskClasses[level].dot}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          <Card>
            <CardHeader
              title="System health"
              description="Step-level reliability across every investigation."
            />
            <dl className="mt-4 space-y-2.5 text-xs">
              <HealthRow
                label="Steps executed"
                value={String(data.system_health.steps_executed)}
              />
              <HealthRow
                label="Step success rate"
                value={formatPercent(data.system_health.success_rate, 0)}
                tone={data.system_health.success_rate < 1 ? 'warn' : 'ok'}
              />
              <HealthRow
                label="Failed steps"
                value={String(data.system_health.failed_steps)}
                tone={data.system_health.failed_steps > 0 ? 'alert' : 'ok'}
              />
              <HealthRow
                label="Schema retries"
                value={formatPercent(data.system_health.schema_retry_rate, 0)}
                tone={data.system_health.schema_retry_rate > 0.2 ? 'warn' : 'ok'}
              />
            </dl>
            <Link
              href="/operations"
              className="mt-4 inline-block text-xs text-accent hover:underline"
            >
              AI Operations detail
            </Link>
          </Card>
        </div>
      </div>

      <Card className="mt-5">
        <CardHeader
          title="Cases requiring attention"
          description="Held by a control, or waiting on a human decision. These do not clear themselves."
        />
        <div className="mt-4">
          {data.attention.length === 0 ? (
            <EmptyState
              title="Nothing is waiting"
              description="No investigation is currently held at the review gate or has failed."
            />
          ) : (
            <ul className="space-y-2.5">
              {data.attention.map((item) => (
                <li
                  key={item.investigation_id}
                  className="flex flex-wrap items-start justify-between gap-3 rounded border border-line bg-raised/50 px-3.5 py-3"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        href={`/cases/${item.case_id}`}
                        className="text-sm font-medium text-ink hover:text-accent"
                      >
                        {item.organisation}
                      </Link>
                      <span className="text-2xs text-ink-subtle">{item.reference}</span>
                      <RiskBadge level={item.overall_level} />
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-ink-muted">{item.reason}</p>
                    {item.escalations.length > 1 ? (
                      <p className="mt-1 text-2xs text-ink-subtle">
                        +{item.escalations.length - 1} further escalation
                        {item.escalations.length > 2 ? 's' : ''}
                      </p>
                    ) : null}
                  </div>
                  <LinkButton href={`/cases/${item.case_id}`} size="sm">
                    Review
                  </LinkButton>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>
    </>
  );
}

function HealthRow({
  label,
  value,
  tone = 'ok',
}: {
  label: string;
  value: string;
  tone?: 'ok' | 'warn' | 'alert';
}) {
  const color =
    tone === 'alert' ? 'text-high' : tone === 'warn' ? 'text-moderate' : 'text-ink';
  return (
    <div className="flex items-baseline justify-between border-b border-line pb-2 last:border-0 last:pb-0">
      <dt className="text-ink-muted">{label}</dt>
      <dd className={`tabular font-medium ${color}`}>{value}</dd>
    </div>
  );
}
