import { EvidenceGraph } from '@/components/graph/evidence-graph';
import { EmptyState, PageHeader } from '@/components/ui/primitives';
import { LinkButton } from '@/components/ui/button';
import { getCases, getGraph } from '@/lib/api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Evidence Graph' };

export default async function GraphPage({
  searchParams,
}: {
  searchParams: { investigation?: string };
}) {
  const cases = await getCases();
  const fallback = cases?.cases.find((item) => item.latest_investigation)?.latest_investigation;
  const investigationId = searchParams.investigation ?? fallback?.id;
  const graph = investigationId ? await getGraph(investigationId) : null;

  return (
    <>
      <PageHeader
        eyebrow="Evidence Graph"
        title="Decision lineage"
        description="Every rating traces back through its findings, the evidence behind them and the documents that evidence came from. Nothing here is inferred - the pipeline stored citations as identifiers, so the lineage is a query."
        actions={
          fallback ? (
            <LinkButton href={`/cases/${fallback.case_id}`} size="lg">
              Open the case
            </LinkButton>
          ) : undefined
        }
      />

      {!graph || graph.nodes.length === 0 ? (
        <EmptyState
          title="No investigation to graph"
          description={
            <>
              Run an investigation first. Seed and run it in one step with{' '}
              <code className="font-mono">make seed-full</code>.
            </>
          }
        />
      ) : (
        <EvidenceGraph data={graph} />
      )}
    </>
  );
}
