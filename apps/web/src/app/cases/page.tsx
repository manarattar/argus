import Link from 'next/link';

import {
  Badge,
  Card,
  EmptyState,
  PageHeader,
  RiskBadge,
  StrengthBadge,
  Table,
  Td,
  Th,
} from '@/components/ui/primitives';
import { getCases } from '@/lib/api';
import { formatDate, formatDuration, titleCase } from '@/lib/format';

export const dynamic = 'force-dynamic';

export const metadata = { title: 'Cases' };

const STATUS_TONE: Record<string, 'ok' | 'warn' | 'alert' | 'muted' | 'accent'> = {
  draft: 'muted',
  investigating: 'accent',
  awaiting_review: 'warn',
  in_review: 'warn',
  approved: 'ok',
  rejected: 'muted',
  escalated: 'alert',
};

export default async function CasesPage() {
  const data = await getCases();

  return (
    <>
      <PageHeader
        eyebrow="Cases"
        title="Counterparty reviews"
        description="Each case is a review of one organisation against a configured risk domain."
      />

      {!data ? (
        <EmptyState
          title="The API is not reachable"
          description={
            <>
              Start the backend with <code className="font-mono">make api</code>.
            </>
          }
        />
      ) : data.cases.length === 0 ? (
        <EmptyState
          title="No cases yet"
          description={
            <>
              Seed the demonstration corpus with <code className="font-mono">make seed</code>.
            </>
          }
        />
      ) : (
        <Card padded={false}>
          <div className="px-5 py-4">
            <Table>
              <thead>
                <tr>
                  <Th>Counterparty</Th>
                  <Th>Review</Th>
                  <Th>Status</Th>
                  <Th>Provisional rating</Th>
                  <Th>Evidence</Th>
                  <Th align="right">Docs</Th>
                  <Th align="right">Last run</Th>
                  <Th>Analyst</Th>
                </tr>
              </thead>
              <tbody>
                {data.cases.map((item) => {
                  const run = item.latest_investigation;
                  return (
                    <tr key={item.id} className="group">
                      <Td>
                        <Link
                          href={`/cases/${item.id}`}
                          className="font-medium text-ink group-hover:text-accent"
                        >
                          {item.organisation}
                        </Link>
                        <span className="mt-0.5 block text-2xs text-ink-subtle">
                          {item.reference} · {item.sector || 'sector not recorded'}
                        </span>
                      </Td>
                      <Td className="text-ink-muted">{item.review_type}</Td>
                      <Td>
                        <Badge tone={STATUS_TONE[item.status] ?? 'muted'}>
                          {titleCase(item.status)}
                        </Badge>
                      </Td>
                      <Td>
                        {run ? (
                          <RiskBadge level={run.overall_level} score={run.overall_score} />
                        ) : (
                          <span className="text-2xs text-ink-subtle">Not investigated</span>
                        )}
                      </Td>
                      <Td>
                        {run?.evidence_strength ? (
                          <StrengthBadge strength={run.evidence_strength} />
                        ) : (
                          <span className="text-2xs text-ink-subtle">—</span>
                        )}
                      </Td>
                      <Td align="right">{item.document_count}</Td>
                      <Td align="right" className="whitespace-nowrap text-ink-muted">
                        {run ? formatDuration(run.duration_ms) : '—'}
                      </Td>
                      <Td className="whitespace-nowrap text-ink-muted">
                        {item.analyst}
                        <span className="mt-0.5 block text-2xs text-ink-subtle">
                          opened {formatDate(item.created_at)}
                        </span>
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </div>
        </Card>
      )}
    </>
  );
}
