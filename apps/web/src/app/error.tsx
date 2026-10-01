'use client';

import { useEffect } from 'react';

import { Button } from '@/components/ui/button';

/**
 * Route-level error boundary. One calm screen instead of a blank page, with
 * the real message underneath: when the backend is down or a step failed, the
 * specific reason is the useful thing to show.
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
    <div role="alert" className="mx-auto mt-10 max-w-xl border border-line border-l-[3px] border-l-high bg-surface p-6 shadow-card">
      <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-high">Page error</p>
      <h1 className="mt-1.5 text-xl font-semibold text-ink">This page stopped working</h1>
      <p className="mt-2 text-sm leading-relaxed text-ink-muted">
        Nothing was changed. Try the page again. If the API is not running, start it with{' '}
        <code className="font-mono text-xs">make api</code> first.
      </p>
      <p className="mt-3 break-words rounded bg-raised px-3 py-2 font-mono text-2xs text-ink-muted">
        {(error.message || 'Unexpected error').slice(0, 240)}
        {error.digest ? ` · ref ${error.digest}` : ''}
      </p>
      <div className="mt-4 flex gap-2">
        <Button variant="primary" onClick={reset}>
          Try again
        </Button>
        <Button onClick={() => window.location.assign('/')}>Back to overview</Button>
      </div>
    </div>
  );
}
