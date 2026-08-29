'use client';

import clsx from 'clsx';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Badge, Card, ErrorState } from '@/components/ui/primitives';
import { ApiError, submitReview } from '@/lib/api';
import { formatDateTime, titleCase } from '@/lib/format';
import type { InvestigationDetail } from '@/lib/types';

const DECISIONS = [
  {
    key: 'approve',
    label: 'Approve',
    hint: 'Accept the assessment as it stands and complete the review.',
    variant: 'primary' as const,
    requiresComment: false,
  },
  {
    key: 'request_deeper_investigation',
    label: 'Request deeper investigation',
    hint: 'Send it back for more evidence before deciding.',
    variant: 'secondary' as const,
    requiresComment: false,
  },
  {
    key: 'escalate',
    label: 'Escalate',
    hint: 'Refer to a senior reviewer. Required when a control has fired.',
    variant: 'secondary' as const,
    requiresComment: true,
  },
  {
    key: 'reject',
    label: 'Reject',
    hint: 'Reject the assessment. Findings and reasoning are retained.',
    variant: 'danger' as const,
    requiresComment: true,
  },
];

/**
 * The human review gate.
 *
 * This is the only route that can complete an investigation. Approval is
 * refused while a mandatory escalation is outstanding - the analyst can still
 * escalate or reject, but cannot approve past a control.
 */
export function ReviewGate({
  investigation,
  onUpdate,
}: {
  investigation: InvestigationDetail;
  onUpdate: (next: Partial<InvestigationDetail>) => void;
}) {
  const [decision, setDecision] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const latestReview = investigation.reviews[0];
  const escalated = investigation.escalation_reasons.length > 0;
  const selected = DECISIONS.find((d) => d.key === decision);
  const commentRequired = selected?.requiresComment ?? false;
  const canSubmit =
    Boolean(decision) && (!commentRequired || comment.trim().length >= 10) && !busy;

  if (investigation.status === 'failed') {
    return (
      <Card>
        <p className="text-sm font-semibold text-high">
          This investigation failed and cannot be reviewed
        </p>
        <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
          A failed run is not presented for approval. Re-run the investigation once the cause in
          the Trace tab is resolved.
        </p>
      </Card>
    );
  }

  if (investigation.status === 'completed' && latestReview) {
    return (
      <Card className="border-low/30 bg-low/5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="ok">Review complete</Badge>
          <span className="text-sm font-medium text-ink">
            {titleCase(latestReview.decision)} by {latestReview.actor}
          </span>
          <span className="text-2xs text-ink-subtle">
            {formatDateTime(latestReview.created_at)}
          </span>
        </div>
        {latestReview.changed_overall_level ? (
          <p className="mt-2 text-xs text-ink-muted">
            The system proposed{' '}
            <span className="font-semibold text-ink">
              {titleCase(latestReview.ai_overall_level || 'none')}
            </span>
            ; the final rating is{' '}
            <span className="font-semibold text-ink">
              {titleCase(latestReview.final_overall_level || 'none')}
            </span>
            . Both are retained on the record.
          </p>
        ) : (
          <p className="mt-2 text-xs text-ink-muted">
            The analyst accepted the system&apos;s proposed rating without change.
          </p>
        )}
        {latestReview.comment ? (
          <p className="mt-2 text-xs leading-relaxed text-ink-muted">
            “{latestReview.comment}”
          </p>
        ) : null}
      </Card>
    );
  }

  async function submit() {
    if (!decision) return;
    setBusy(true);
    setError(null);
    try {
      const response = await submitReview(investigation.id, decision, comment);
      onUpdate(response.investigation);
      window.setTimeout(() => window.location.reload(), 300);
    } catch (exc) {
      setError(
        exc instanceof ApiError ? exc.message : 'The decision could not be recorded.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="border-accent/30">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-ink">Human review gate</h2>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-ink-muted">
            The workflow stops here by construction. Nothing completes this assessment except a
            recorded decision by a named person, and your decision is stored alongside what the
            system proposed.
          </p>
        </div>
        <Badge tone="warn">Awaiting decision</Badge>
      </div>

      {escalated ? (
        <p className="mt-3 rounded border border-high/30 bg-high/5 px-3.5 py-2.5 text-xs leading-relaxed text-ink-muted">
          <span className="font-semibold text-high">Approval is blocked. </span>
          A mandatory escalation rule has fired, so this assessment must be escalated or rejected
          rather than approved directly.
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        {DECISIONS.map((option) => {
          const blocked = option.key === 'approve' && escalated;
          return (
            <button
              key={option.key}
              type="button"
              disabled={blocked}
              title={blocked ? 'Blocked by a mandatory escalation rule.' : option.hint}
              onClick={() => setDecision(decision === option.key ? null : option.key)}
              className={clsx(
                'rounded border px-3 py-2 text-left text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-40',
                decision === option.key
                  ? 'border-accent bg-accent-soft text-accent'
                  : 'border-line bg-surface text-ink-muted hover:border-line-strong hover:text-ink',
              )}
            >
              <span className="block font-medium">{option.label}</span>
              <span className="mt-0.5 block text-2xs opacity-80">{option.hint}</span>
            </button>
          );
        })}
      </div>

      {decision ? (
        <div className="mt-4">
          <label
            htmlFor="review-comment"
            className="mb-1.5 block text-2xs font-medium uppercase tracking-[0.08em] text-ink-subtle"
          >
            {commentRequired ? 'Reason (required)' : 'Comment (optional)'}
          </label>
          <textarea
            id="review-comment"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            rows={3}
            placeholder={
              commentRequired
                ? 'Why are you taking this decision? This is recorded in the audit trail.'
                : 'Anything a senior reviewer should know.'
            }
            className="w-full rounded border border-line bg-surface px-3 py-2 text-xs text-ink placeholder:text-ink-subtle focus:border-accent"
          />
          {commentRequired && comment.trim().length < 10 ? (
            <p className="mt-1 text-2xs text-ink-subtle">
              At least 10 characters required ({comment.trim().length}/10).
            </p>
          ) : null}
        </div>
      ) : null}

      {error ? (
        <div className="mt-4">
          <ErrorState title="Decision not recorded" detail={error} />
        </div>
      ) : null}

      <div className="mt-4 flex items-center gap-3">
        <Button
          variant={selected?.variant ?? 'primary'}
          size="lg"
          disabled={!canSubmit}
          loading={busy}
          onClick={submit}
        >
          {selected ? `Record: ${selected.label}` : 'Select a decision'}
        </Button>
        <p className="text-2xs text-ink-subtle">
          {investigation.overrides.length} adjustment
          {investigation.overrides.length === 1 ? '' : 's'} made to this assessment.
        </p>
      </div>
    </Card>
  );
}
