'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { ApiError, runInvestigation } from '@/lib/api';

/**
 * Starts the investigation graph.
 *
 * The run is synchronous and takes seconds, so the button reports progress
 * rather than pretending to stream. On failure it shows the API's own message -
 * in Demo Mode that message is usually "no recording for this step", which is
 * genuinely the most useful thing to tell the user.
 */
export function StartInvestigation({
  caseId,
  hasInvestigation,
}: {
  caseId: string;
  hasInvestigation: boolean;
}) {
  const router = useRouter();
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setRunning(true);
    setError(null);
    try {
      await runInvestigation(caseId);
      router.refresh();
    } catch (exc) {
      setError(
        exc instanceof ApiError
          ? exc.message
          : 'The investigation could not be started. Is the API running?',
      );
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <Button
        variant={hasInvestigation ? 'secondary' : 'primary'}
        size="lg"
        onClick={start}
        loading={running}
      >
        {running
          ? 'Running investigation…'
          : hasInvestigation
            ? 'Re-run investigation'
            : 'Start investigation'}
      </Button>
      {error ? (
        <p className="max-w-md text-right text-2xs leading-relaxed text-high">{error}</p>
      ) : null}
    </div>
  );
}
