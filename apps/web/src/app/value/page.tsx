import { ValueCase } from '@/components/value/value-case';
import { EmptyState, PageHeader } from '@/components/ui/primitives';
import { getValueCaseDefaults } from '@/lib/api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Value Case' };

export default async function ValuePage() {
  const data = await getValueCaseDefaults();

  return (
    <>
      <PageHeader
        eyebrow="Value Case"
        title="What this would be worth"
        description="An illustrative model over assumptions you can change. Deliberately conservative: the saving applies to preparation time only, review and sign-off are unchanged, and the benefit is scaled by adoption."
      />
      {!data ? (
        <EmptyState title="The API is not reachable" description="Start the backend and reload." />
      ) : (
        <ValueCase
          defaults={data.assumptions}
          notes={data.notes}
          disclaimer={data.disclaimer}
        />
      )}
    </>
  );
}
