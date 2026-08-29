'use client';

import clsx from 'clsx';

import { Badge, Card, CardHeader, EmptyState, Mono } from '@/components/ui/primitives';
import { formatDateTime, titleCase } from '@/lib/format';
import type { AuditEvent } from '@/lib/types';

const ACTOR_TONE = {
  human: 'accent',
  ai: 'muted',
  system: 'muted',
} as const;

/**
 * The audit trail is append-only and rendered in reverse chronological order.
 * Human actions are visually distinguished because the question an auditor asks
 * first is "who decided this?".
 */
export function AuditPanel({ events }: { events: AuditEvent[] }) {
  if (events.length === 0) {
    return (
      <EmptyState
        title="No audit events yet"
        description="Every case action - documents ingested, investigation run, severity overridden, review submitted - is appended here."
      />
    );
  }

  return (
    <Card>
      <CardHeader
        title="Audit trail"
        description="Append-only. Nothing in this application can update or delete an entry."
      />
      <ol className="mt-4 space-y-0">
        {events.map((event, index) => (
          <li key={event.id} className="flex gap-3.5">
            <div className="flex flex-col items-center">
              <span
                className={clsx(
                  'mt-1.5 h-2 w-2 shrink-0 rounded-full',
                  event.actor_type === 'human' ? 'bg-accent' : 'bg-line-strong',
                )}
              />
              {index < events.length - 1 ? (
                <span className="w-px flex-1 bg-line" />
              ) : null}
            </div>
            <div className="min-w-0 flex-1 pb-4">
              <div className="flex flex-wrap items-center gap-2">
                <Mono>{event.action}</Mono>
                <Badge tone={ACTOR_TONE[event.actor_type]}>{titleCase(event.actor_type)}</Badge>
                <span className="text-2xs text-ink-subtle">
                  {event.actor} · {formatDateTime(event.created_at)}
                </span>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-ink-muted">{event.summary}</p>
              {Object.keys(event.before).length > 0 || Object.keys(event.after).length > 0 ? (
                <details className="mt-1.5">
                  <summary className="cursor-pointer text-2xs text-ink-subtle hover:text-ink">
                    Before / after
                  </summary>
                  <pre className="scroll-slim mt-1.5 max-h-40 overflow-auto rounded bg-raised px-2.5 py-2 font-mono text-2xs text-ink-muted">
{JSON.stringify({ before: event.before, after: event.after }, null, 2)}
                  </pre>
                </details>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}
