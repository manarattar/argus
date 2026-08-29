import { LinkButton } from '@/components/ui/button';
import { EmptyState, PageHeader } from '@/components/ui/primitives';

export default function NotFound() {
  return (
    <>
      <PageHeader eyebrow="404" title="Not found" />
      <EmptyState
        title="That page or record does not exist"
        description="It may have been removed, or the identifier may be wrong."
        action={<LinkButton href="/" variant="primary">Back to overview</LinkButton>}
      />
    </>
  );
}
