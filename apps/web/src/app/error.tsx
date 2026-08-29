'use client';

import { useEffect } from 'react';

import { Button } from '@/components/ui/button';
import { ErrorState, PageHeader } from '@/components/ui/primitives';

/**
 * Route-level error boundary. Shows the real message rather than a generic
 * apology: when the backend is down or a step failed, the specific reason is
 * the useful thing to display.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[argus] route error', error);
  }, [error]);

  return (
    <>
      <PageHeader eyebrow="Error" title="This page could not be loaded" />
      <ErrorState
        title={error.message || 'Unexpected error'}
        detail={
          <>
            <p>
              If the API is not running, start it with <code className="font-mono">make api</code>{' '}
              and try again.
            </p>
            {error.digest ? (
              <p className="mt-1.5 font-mono text-2xs">reference: {error.digest}</p>
            ) : null}
          </>
        }
        action={
          <Button variant="primary" onClick={reset}>
            Try again
          </Button>
        }
      />
    </>
  );
}
