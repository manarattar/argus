import { EvaluationLab } from '@/components/evaluation/evaluation-lab';
import { PageHeader } from '@/components/ui/primitives';
import { getEvaluationCases, getLatestEvaluation } from '@/lib/api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Evaluation Lab' };

export default async function EvaluationPage() {
  const [latest, suite] = await Promise.all([getLatestEvaluation(), getEvaluationCases()]);

  return (
    <>
      <PageHeader
        eyebrow="Evaluation Lab"
        title="How well does this actually work"
        description="A reproducible suite over the reference corpus. Pass rate is computed over executed cases only, and coverage reports how much of the suite ran - so a result cannot look strong by not running."
      />
      <EvaluationLab
        initialRun={latest?.run ?? null}
        suite={suite ?? null}
        emptyMessage={latest?.message}
      />
    </>
  );
}
