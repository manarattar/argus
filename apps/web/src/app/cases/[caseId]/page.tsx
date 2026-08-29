import { notFound } from 'next/navigation';

import { InvestigationWorkspace } from '@/components/investigation/workspace';
import { StartInvestigation } from '@/components/investigation/start';
import {
  Card,
  CardHeader,
  DefinitionRow,
  EmptyState,
  PageHeader,
  Table,
  Td,
  Th,
} from '@/components/ui/primitives';
import { getCase, getCaseAudit, getInvestigation, getSuggestedQuestions } from '@/lib/api';
import { formatNumber } from '@/lib/format';

export const dynamic = 'force-dynamic';

export async function generateMetadata({ params }: { params: { caseId: string } }) {
  const detail = await getCase(params.caseId);
  return { title: detail ? detail.organisation : 'Case' };
}

export default async function CasePage({ params }: { params: { caseId: string } }) {
  const detail = await getCase(params.caseId);
  if (!detail) {
    notFound();
  }

  const latest = detail.latest_investigation;
  const [investigation, audit, suggested] = await Promise.all([
    latest ? getInvestigation(detail.id, latest.id) : Promise.resolve(null),
    getCaseAudit(detail.id),
    latest ? getSuggestedQuestions(latest.id) : Promise.resolve(null),
  ]);

  return (
    <>
      <PageHeader
        eyebrow={detail.reference}
        title={detail.organisation}
        description={
          <>
            {detail.review_type} · {detail.sector || 'sector not recorded'} ·{' '}
            {detail.jurisdiction || 'jurisdiction not recorded'} · assigned to {detail.analyst}
          </>
        }
        actions={<StartInvestigation caseId={detail.id} hasInvestigation={Boolean(latest)} />}
      />

      {investigation ? (
        <InvestigationWorkspace
          caseId={detail.id}
          initial={investigation}
          auditEvents={audit?.events ?? []}
          suggestedQuestions={suggested?.questions ?? []}
        />
      ) : (
        <div className="grid gap-5 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader
              title="No investigation has run for this case"
              description="Start one to extract evidence, identify risks, match them against policy, challenge them and compute a provisional rating."
            />
            <div className="mt-4">
              <EmptyState
                title="Ready to investigate"
                description="The graph runs eight steps and stops at the human review gate. Nothing is finalised without your decision."
                action={<StartInvestigation caseId={detail.id} hasInvestigation={false} />}
              />
            </div>
          </Card>

          <Card>
            <CardHeader title="Case file" description="Documents available to the investigation." />
            <dl className="mt-3">
              <DefinitionRow term="Reference">{detail.reference}</DefinitionRow>
              <DefinitionRow term="Review type">{detail.review_type}</DefinitionRow>
              <DefinitionRow term="Analyst">{detail.analyst}</DefinitionRow>
              <DefinitionRow term="Background">{detail.background}</DefinitionRow>
            </dl>
            <div className="mt-4">
              <Table>
                <thead>
                  <tr>
                    <Th>Document</Th>
                    <Th align="right">Chunks</Th>
                  </tr>
                </thead>
                <tbody>
                  {detail.documents.map((document) => (
                    <tr key={document.id}>
                      <Td>
                        {document.name}
                        <span className="mt-0.5 block text-2xs text-ink-subtle">
                          {formatNumber(document.characters)} characters · synthetic
                        </span>
                      </Td>
                      <Td align="right">{document.chunks}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
