import { AuditPanel } from '@/components/investigation/audit';
import { EmptyState, PageHeader } from '@/components/ui/primitives';
import { getGlobalAudit } from '@/lib/api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Audit Trail' };

export default async function AuditPage() {
  const data = await getGlobalAudit();

  return (
    <>
      <PageHeader
        eyebrow="Audit"
        title="Audit trail"
        description="Append-only record of every action across every case: documents ingested, investigations run, findings adjusted, decisions taken. No code path in this application can update or delete an entry."
      />
      {!data ? (
        <EmptyState
          title="The API is not reachable"
          description="Start the backend and reload."
        />
      ) : (
        <AuditPanel events={data.events} />
      )}
    </>
  );
}
