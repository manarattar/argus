import { ScenarioLab } from '@/components/scenario/scenario-lab';
import { EmptyState, PageHeader } from '@/components/ui/primitives';
import { getCases, getScenarioVariables } from '@/lib/api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Scenario Lab' };

export default async function ScenarioPage({
  searchParams,
}: {
  searchParams: { investigation?: string };
}) {
  const cases = await getCases();
  const fallback = cases?.cases.find((item) => item.latest_investigation)?.latest_investigation;
  const investigationId = searchParams.investigation ?? fallback?.id;
  const data = investigationId ? await getScenarioVariables(investigationId) : null;

  return (
    <>
      <PageHeader
        eyebrow="Scenario Lab"
        title="What would change the assessment"
        description="Vary a structured input that the case evidence actually contains, and see the rating recomputed by the same deterministic engine. Simulations, not findings."
      />

      {!data || !investigationId ? (
        <EmptyState
          title="No investigation to model"
          description="Run an investigation first, then return here to explore how its inputs move the rating."
        />
      ) : (
        <ScenarioLab
          investigationId={investigationId}
          variables={data.variables}
          note={data.note}
        />
      )}
    </>
  );
}
