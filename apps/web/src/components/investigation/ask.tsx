'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Badge,
  Card,
  CardHeader,
  Callout,
  ErrorState,
  Mono,
  SectionLabel,
} from '@/components/ui/primitives';
import { ApiError, askArgus } from '@/lib/api';
import { formatDuration } from '@/lib/format';
import type { GroundedAnswer, InvestigationDetail } from '@/lib/types';

/**
 * Ask ARGUS - a secondary, grounded question-answering surface.
 *
 * Deliberately not the primary interface. The product's value is the structured
 * investigation; conversation is a way to interrogate that record, not a
 * replacement for it.
 *
 * The refusal path is treated as a first-class result: when the case record
 * cannot answer, that answer is displayed as clearly as any other, because a
 * stated gap is more useful to an analyst than a plausible guess.
 */
export function AskPanel({
  investigation,
  suggestedQuestions,
}: {
  investigation: InvestigationDetail;
  suggestedQuestions: string[];
}) {
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState<{ question: string; answer: GroundedAnswer }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const evidenceById = new Map(investigation.evidence.map((e) => [e.evidence_id, e]));

  async function ask(value: string) {
    const trimmed = value.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      const answer = await askArgus(investigation.id, trimmed);
      setHistory((current) => [{ question: trimmed, answer }, ...current]);
      setQuestion('');
    } catch (exc) {
      setError(
        exc instanceof ApiError
          ? exc.message
          : 'The question could not be answered. Check the API is available.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <div className="space-y-5 lg:col-span-2">
        <Card>
          <CardHeader
            title="Ask ARGUS"
            description="Answers come from this case's evidence, findings, policy matches and challenges. Nothing else."
          />
          <form
            className="mt-4"
            onSubmit={(event) => {
              event.preventDefault();
              void ask(question);
            }}
          >
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              rows={3}
              maxLength={600}
              placeholder="Why did governance risk receive this rating? What evidence contradicts the concentration finding?"
              className="w-full rounded border border-line bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-ink-subtle focus:border-accent"
              onKeyDown={(event) => {
                if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                  event.preventDefault();
                  void ask(question);
                }
              }}
            />
            <div className="mt-2 flex items-center justify-between">
              <p className="text-2xs text-ink-subtle">
                {question.length}/600 · Ctrl+Enter to send
              </p>
              <Button type="submit" variant="primary" loading={busy} disabled={!question.trim()}>
                Ask
              </Button>
            </div>
          </form>

          {error ? (
            <div className="mt-4">
              <ErrorState title="Could not answer" detail={error} />
            </div>
          ) : null}
        </Card>

        {history.map((entry, index) => (
          <Card key={`${entry.question}-${index}`}>
            <p className="text-sm font-medium text-ink">{entry.question}</p>

            {entry.answer.answerable ? (
              <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-ink-muted">
                {entry.answer.answer}
              </p>
            ) : (
              <div className="mt-3">
                <Callout tone="warn" title="The case record does not answer this">
                  <p>{entry.answer.answer}</p>
                  {entry.answer.insufficient_evidence_note ? (
                    <p className="mt-1.5">{entry.answer.insufficient_evidence_note}</p>
                  ) : null}
                </Callout>
              </div>
            )}

            {entry.answer.citations.length > 0 ? (
              <div className="mt-4">
                <SectionLabel>Citations ({entry.answer.citations.length})</SectionLabel>
                <ul className="space-y-2">
                  {entry.answer.citations.map((citation) => {
                    const known = evidenceById.has(citation.evidence_id);
                    return (
                      <li
                        key={citation.evidence_id}
                        className="rounded border-l-2 border-accent/50 py-1 pl-3"
                      >
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Mono>{citation.evidence_id}</Mono>
                          <span className="text-2xs text-ink-subtle">
                            {citation.document_name}, {citation.section_reference}
                          </span>
                          {!known ? (
                            <Badge tone="alert" title="This citation did not resolve to stored evidence.">
                              unresolved
                            </Badge>
                          ) : null}
                        </div>
                        <p className="mt-1 text-2xs italic leading-relaxed text-ink-muted">
                          “{citation.quote}”
                        </p>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : entry.answer.answerable ? (
              <p className="mt-3 text-2xs text-moderate">
                This answer carries no citations. Treat it with corresponding caution.
              </p>
            ) : null}

            <p className="mt-4 border-t border-line pt-2.5 text-2xs text-ink-subtle">
              {entry.answer.replayed ? 'Replayed response' : entry.answer.model} ·{' '}
              {formatDuration(entry.answer.latency_ms)}
              {entry.answer.estimated_cost_usd
                ? ` · ~$${entry.answer.estimated_cost_usd.toFixed(5)}`
                : ''}
            </p>
          </Card>
        ))}
      </div>

      <div className="space-y-5">
        <Card>
          <CardHeader
            title="Suggested questions"
            description="Generated from this investigation's actual findings, so they always refer to something the case contains."
          />
          <ul className="mt-3 space-y-1.5">
            {suggestedQuestions.map((suggestion) => (
              <li key={suggestion}>
                <button
                  onClick={() => void ask(suggestion)}
                  disabled={busy}
                  className="w-full rounded border border-line px-3 py-2 text-left text-xs text-ink-muted transition-colors hover:border-accent/40 hover:bg-accent-soft hover:text-ink disabled:opacity-50"
                >
                  {suggestion}
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <CardHeader title="How answers are constrained" />
          <ul className="mt-3 space-y-2 text-2xs leading-relaxed text-ink-muted">
            <li>
              · Only this case&apos;s stored evidence, findings, policy matches and challenges
              are supplied.
            </li>
            <li>· Citations are checked against stored evidence ids before display; anything that does not resolve is removed.</li>
            <li>· When the record cannot answer, the response says so rather than reaching for general knowledge.</li>
            <li>· Document text is supplied as untrusted, delimited data - never as instruction.</li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
