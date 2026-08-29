'use client';

import clsx from 'clsx';
import { useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Mono,
  SectionLabel,
  StrengthBadge,
  TriggerBadge,
  VerificationBadge,
} from '@/components/ui/primitives';
import {
  ApiError,
  addNote,
  markFalsePositive,
  requestChallenge,
  setLikelihood,
  setSeverity,
} from '@/lib/api';
import { titleCase } from '@/lib/format';
import type { Challenge, EvidenceItem, InvestigationDetail, RiskFinding } from '@/lib/types';

const SEVERITIES = ['negligible', 'minor', 'moderate', 'major', 'severe'] as const;
const LIKELIHOODS = ['rare', 'unlikely', 'possible', 'likely', 'almost_certain'] as const;

export function FindingsPanel({
  investigation,
  onUpdate,
  focusRisk,
  onFocusHandled,
}: {
  investigation: InvestigationDetail;
  onUpdate: (next: Partial<InvestigationDetail>) => void;
  focusRisk: string | null;
  onFocusHandled: () => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(
    investigation.risks[0]?.risk_id ?? null,
  );

  useEffect(() => {
    if (focusRisk) {
      setExpanded(focusRisk);
      document.getElementById(`finding-${focusRisk}`)?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
      onFocusHandled();
    }
  }, [focusRisk, onFocusHandled]);

  const evidenceById = new Map(investigation.evidence.map((e) => [e.evidence_id, e]));
  const active = investigation.risks.filter((r) => !r.is_false_positive);
  const dismissed = investigation.risks.filter((r) => r.is_false_positive);

  if (investigation.risks.length === 0) {
    return (
      <EmptyState
        title="No findings were produced"
        description="The investigation completed without identifying a risk the evidence supports. That is a finding in itself and should be reviewed rather than assumed correct."
      />
    );
  }

  return (
    <div className="space-y-3">
      {active.map((finding) => (
        <FindingCard
          key={finding.risk_id}
          finding={finding}
          investigation={investigation}
          evidenceById={evidenceById}
          expanded={expanded === finding.risk_id}
          onToggle={() =>
            setExpanded(expanded === finding.risk_id ? null : finding.risk_id)
          }
          onUpdate={onUpdate}
        />
      ))}

      {dismissed.length > 0 ? (
        <Card>
          <CardHeader
            title={`${dismissed.length} finding${dismissed.length === 1 ? '' : 's'} marked as false positive`}
            description="Retained for the record and excluded from the rating. Nothing is deleted."
          />
          <ul className="mt-3 space-y-2">
            {dismissed.map((finding) => (
              <li key={finding.risk_id} className="flex items-center gap-2.5 text-xs">
                <Badge tone="muted">false positive</Badge>
                <span className="text-ink-muted line-through">{finding.title}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}

function FindingCard({
  finding,
  investigation,
  evidenceById,
  expanded,
  onToggle,
  onUpdate,
}: {
  finding: RiskFinding;
  investigation: InvestigationDetail;
  evidenceById: Map<string, EvidenceItem>;
  expanded: boolean;
  onToggle: () => void;
  onUpdate: (next: Partial<InvestigationDetail>) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [challenges, setChallenges] = useState<Challenge[]>(finding.challenges);
  const [note, setNote] = useState(finding.analyst_note);
  const [editing, setEditing] = useState<'severity' | 'likelihood' | 'false-positive' | null>(
    null,
  );

  const supporting = finding.supporting_evidence_ids
    .map((id) => evidenceById.get(id))
    .filter((e): e is EvidenceItem => Boolean(e));
  const contradicting = finding.contradicting_evidence_ids
    .map((id) => evidenceById.get(id))
    .filter((e): e is EvidenceItem => Boolean(e));

  async function applyAction(action: () => Promise<{ assessment?: unknown }>) {
    setBusy(true);
    setError(null);
    try {
      const response = await action();
      const assessment = response.assessment as
        | {
            overall_level: string;
            overall_score: number;
            factors: InvestigationDetail['score_factors'];
            category_levels: Record<string, never>;
            escalation_reasons: string[];
          }
        | undefined;
      if (assessment) {
        onUpdate({
          overall_level: assessment.overall_level as InvestigationDetail['overall_level'],
          overall_score: assessment.overall_score,
          score_factors: assessment.factors,
          category_levels: assessment.category_levels,
          escalation_reasons: assessment.escalation_reasons,
        });
      }
      setEditing(null);
      // The caller refreshes on navigation; a full reload here would lose the
      // analyst's place in a long findings list.
      window.setTimeout(() => window.location.reload(), 350);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'The change could not be saved.');
    } finally {
      setBusy(false);
    }
  }

  async function challenge() {
    setBusy(true);
    setError(null);
    try {
      const response = await requestChallenge(investigation.id, finding.risk_id);
      setChallenges(response.challenges as Challenge[]);
    } catch (exc) {
      setError(
        exc instanceof ApiError
          ? exc.message
          : 'The Challenger could not run. Check the API is available.',
      );
    } finally {
      setBusy(false);
    }
  }

  async function saveNote() {
    setBusy(true);
    setError(null);
    try {
      await addNote(investigation.id, finding.risk_id, note);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'The note could not be saved.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card id={`finding-${finding.risk_id}`} padded={false} className="overflow-hidden">
      <button
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-start justify-between gap-4 px-5 py-4 text-left hover:bg-raised/50"
      >
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-ink">{finding.title}</h3>
            <Badge tone="muted">{finding.category_label}</Badge>
            {finding.was_overridden ? (
              <Badge
                tone="accent"
                title={`AI recommended ${finding.ai_severity} / ${finding.ai_likelihood}`}
              >
                analyst adjusted
              </Badge>
            ) : null}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <SeverityChip label="Severity" value={finding.severity_label} />
            <SeverityChip label="Likelihood" value={finding.likelihood_label} />
            <StrengthBadge
              strength={finding.evidence_strength}
              rationale={finding.strength_rationale}
            />
            {finding.verification ? (
              <VerificationBadge status={finding.verification.status} />
            ) : null}
            {challenges.length > 0 ? (
              <Badge tone={challenges.some((c) => c.unresolved) ? 'warn' : 'muted'}>
                {challenges.length} challenge{challenges.length === 1 ? '' : 's'}
              </Badge>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <div className="text-right">
            <p className="text-2xs uppercase tracking-[0.08em] text-ink-subtle">Score</p>
            <p className="tabular text-sm font-semibold text-ink">
              {finding.adjusted_score.toFixed(1)}
              <span className="text-2xs font-normal text-ink-subtle">/25</span>
            </p>
          </div>
          <svg
            viewBox="0 0 20 20"
            className={clsx(
              'h-4 w-4 text-ink-subtle transition-transform',
              expanded && 'rotate-180',
            )}
            fill="currentColor"
            aria-hidden
          >
            <path d="M5.3 7.3a1 1 0 0 1 1.4 0L10 10.6l3.3-3.3a1 1 0 1 1 1.4 1.4l-4 4a1 1 0 0 1-1.4 0l-4-4a1 1 0 0 1 0-1.4Z" />
          </svg>
        </div>
      </button>

      {expanded ? (
        <div className="border-t border-line px-5 py-4">
          <p className="text-xs leading-relaxed text-ink-muted">{finding.description}</p>

          {error ? (
            <div className="mt-3">
              <ErrorState detail={error} />
            </div>
          ) : null}

          <div className="mt-5 grid gap-5 lg:grid-cols-2">
            <div>
              <SectionLabel>Supporting evidence ({supporting.length})</SectionLabel>
              {supporting.length === 0 ? (
                <p className="text-2xs text-ink-subtle">
                  No citation survived grounding verification, which is why this finding is
                  banded as insufficient evidence.
                </p>
              ) : (
                <ul className="space-y-2.5">
                  {supporting.map((item) => (
                    <EvidenceLine key={item.evidence_id} item={item} tone="support" />
                  ))}
                </ul>
              )}
            </div>

            <div>
              <SectionLabel>Contradicting evidence ({contradicting.length})</SectionLabel>
              {contradicting.length === 0 ? (
                <p className="text-2xs text-ink-subtle">
                  No evidence on file cuts against this finding.
                </p>
              ) : (
                <ul className="space-y-2.5">
                  {contradicting.map((item) => (
                    <EvidenceLine key={item.evidence_id} item={item} tone="contradict" />
                  ))}
                </ul>
              )}
            </div>
          </div>

          {finding.verification ? (
            <div className="mt-5 rounded border border-line bg-raised/40 px-3.5 py-3">
              <div className="flex items-center gap-2">
                <SectionLabel>Verifier</SectionLabel>
                <span className="mb-2">
                  <VerificationBadge status={finding.verification.status} />
                </span>
              </div>
              <p className="text-2xs leading-relaxed text-ink-muted">
                {finding.verification.reasoning}
              </p>
              {finding.verification.irrelevant_citation_ids.length > 0 ? (
                <p className="mt-1.5 text-2xs text-ink-subtle">
                  Citations judged not relevant:{' '}
                  {finding.verification.irrelevant_citation_ids.map((id) => (
                    <Mono key={id} className="mr-1">
                      {id}
                    </Mono>
                  ))}
                </p>
              ) : null}
            </div>
          ) : null}

          {finding.policy_matches.length > 0 ? (
            <div className="mt-5">
              <SectionLabel>Policy</SectionLabel>
              <ul className="space-y-2">
                {finding.policy_matches.map((match) => (
                  <li key={match.match_id} className="rounded border border-line px-3.5 py-2.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <Mono>{match.clause_reference}</Mono>
                      <span className="text-xs font-medium text-ink">{match.clause_title}</span>
                      <TriggerBadge trigger={match.trigger_type} />
                    </div>
                    <p className="mt-1.5 text-2xs leading-relaxed text-ink-muted">
                      {match.relevance}
                    </p>
                    {match.threshold_assessment ? (
                      <p className="mt-1 text-2xs text-ink-muted">
                        <span className="font-semibold">Threshold: </span>
                        {match.threshold_assessment}
                      </p>
                    ) : null}
                    {match.sufficiency_caveat ? (
                      <p className="mt-1 text-2xs italic text-ink-subtle">
                        {match.sufficiency_caveat}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {(finding.mitigating_factors.length > 0 ||
            finding.assumptions.length > 0 ||
            finding.open_questions.length > 0) ? (
            <div className="mt-5 grid gap-5 md:grid-cols-3">
              <ListBlock label="Mitigating factors" items={finding.mitigating_factors} />
              <ListBlock label="Assumptions" items={finding.assumptions} />
              <ListBlock label="Open questions" items={finding.open_questions} />
            </div>
          ) : null}

          {(finding.mind_changer_increase || finding.mind_changer_decrease) ? (
            <div className="mt-5 rounded border border-line bg-raised/40 px-3.5 py-3">
              <SectionLabel>What would change my mind</SectionLabel>
              {finding.mind_changer_increase ? (
                <p className="text-2xs leading-relaxed text-ink-muted">
                  <span className="font-semibold text-high">Would raise it: </span>
                  {finding.mind_changer_increase}
                </p>
              ) : null}
              {finding.mind_changer_decrease ? (
                <p className="mt-1 text-2xs leading-relaxed text-ink-muted">
                  <span className="font-semibold text-low">Would lower it: </span>
                  {finding.mind_changer_decrease}
                </p>
              ) : null}
            </div>
          ) : null}

          <ChallengeBlock challenges={challenges} onChallenge={challenge} busy={busy} />

          {finding.overrides.length > 0 ? (
            <div className="mt-5">
              <SectionLabel>Analyst adjustments</SectionLabel>
              <ul className="space-y-2">
                {finding.overrides.map((override) => (
                  <li
                    key={override.id}
                    className="rounded border border-accent/25 bg-accent-soft/60 px-3.5 py-2.5 text-2xs"
                  >
                    <p className="font-medium text-ink">
                      {titleCase(override.field)}: AI recommended{' '}
                      <span className="font-semibold">{titleCase(override.ai_value)}</span>, analyst
                      decided <span className="font-semibold">{titleCase(override.human_value)}</span>
                    </p>
                    <p className="mt-1 leading-relaxed text-ink-muted">{override.rationale}</p>
                    <p className="mt-1 text-ink-subtle">
                      {override.actor} · {new Date(override.created_at).toLocaleString('en-GB')}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {/* Analyst controls */}
          <div className="mt-5 border-t border-line pt-4">
            <SectionLabel>Analyst actions</SectionLabel>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => setEditing(editing === 'severity' ? null : 'severity')}>
                Change severity
              </Button>
              <Button
                size="sm"
                onClick={() => setEditing(editing === 'likelihood' ? null : 'likelihood')}
              >
                Change likelihood
              </Button>
              <Button size="sm" onClick={challenge} loading={busy}>
                Challenge this finding
              </Button>
              <Button
                size="sm"
                variant="danger"
                onClick={() =>
                  setEditing(editing === 'false-positive' ? null : 'false-positive')
                }
              >
                Mark false positive
              </Button>
            </div>

            {editing === 'severity' ? (
              <OverrideForm
                label="New severity"
                options={SEVERITIES}
                current={finding.severity}
                aiValue={finding.ai_severity}
                busy={busy}
                onCancel={() => setEditing(null)}
                onSubmit={(value, rationale) =>
                  applyAction(() =>
                    setSeverity(investigation.id, finding.risk_id, value, rationale),
                  )
                }
              />
            ) : null}

            {editing === 'likelihood' ? (
              <OverrideForm
                label="New likelihood"
                options={LIKELIHOODS}
                current={finding.likelihood}
                aiValue={finding.ai_likelihood}
                busy={busy}
                onCancel={() => setEditing(null)}
                onSubmit={(value, rationale) =>
                  applyAction(() =>
                    setLikelihood(investigation.id, finding.risk_id, value, rationale),
                  )
                }
              />
            ) : null}

            {editing === 'false-positive' ? (
              <OverrideForm
                label="Mark as false positive"
                options={null}
                current=""
                aiValue={finding.severity}
                busy={busy}
                onCancel={() => setEditing(null)}
                onSubmit={(_value, rationale) =>
                  applyAction(() =>
                    markFalsePositive(investigation.id, finding.risk_id, rationale),
                  )
                }
              />
            ) : null}

            <div className="mt-4">
              <label
                htmlFor={`note-${finding.risk_id}`}
                className="mb-1.5 block text-2xs font-medium uppercase tracking-[0.08em] text-ink-subtle"
              >
                Analyst note
              </label>
              <textarea
                id={`note-${finding.risk_id}`}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                rows={2}
                placeholder="Context for the reviewer…"
                className="w-full rounded border border-line bg-surface px-3 py-2 text-xs text-ink placeholder:text-ink-subtle focus:border-accent"
              />
              <Button
                size="sm"
                className="mt-2"
                onClick={saveNote}
                loading={busy}
                disabled={!note.trim() || note === finding.analyst_note}
              >
                Save note
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

function SeverityChip({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded border border-line bg-raised px-1.5 py-0.5 text-2xs">
      <span className="text-ink-subtle">{label}</span>
      <span className="font-medium text-ink">{value}</span>
    </span>
  );
}

function EvidenceLine({
  item,
  tone,
}: {
  item: EvidenceItem;
  tone: 'support' | 'contradict';
}) {
  return (
    <li
      className={clsx(
        'rounded border-l-2 py-1 pl-3',
        tone === 'support' ? 'border-accent/50' : 'border-moderate/60',
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Mono>{item.evidence_id}</Mono>
        {item.kind === 'interpretation' ? (
          <Badge tone="muted" title="The model's reading, not a stated fact.">
            interpretation
          </Badge>
        ) : null}
        <span
          className="text-2xs text-ink-subtle"
          title={`Quote matched the source at ${(item.grounding_score * 100).toFixed(0)}%`}
        >
          {item.document_name}, {item.section_reference}
        </span>
      </div>
      <p className="mt-1 text-2xs leading-relaxed text-ink">{item.statement}</p>
      <p className="mt-1 border-l border-line pl-2 text-2xs italic leading-relaxed text-ink-muted">
        “{item.quote}”
      </p>
    </li>
  );
}

function ListBlock({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <SectionLabel>{label}</SectionLabel>
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li key={item} className="flex gap-2 text-2xs leading-relaxed text-ink-muted">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-line-strong" />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ChallengeBlock({
  challenges,
  onChallenge,
  busy,
}: {
  challenges: Challenge[];
  onChallenge: () => void;
  busy: boolean;
}) {
  if (challenges.length === 0) {
    return (
      <div className="mt-5 rounded border border-dashed border-line px-3.5 py-3">
        <p className="text-2xs text-ink-muted">
          No challenge has been raised against this finding.{' '}
          <button
            onClick={onChallenge}
            disabled={busy}
            className="font-medium text-accent hover:underline disabled:opacity-50"
          >
            Ask the Challenger to argue against it
          </button>
          .
        </p>
      </div>
    );
  }

  return (
    <div className="mt-5">
      <SectionLabel>Challenges</SectionLabel>
      <ul className="space-y-2">
        {challenges.map((challenge) => (
          <li
            key={challenge.challenge_id}
            className={clsx(
              'rounded border px-3.5 py-2.5',
              challenge.unresolved ? 'border-moderate/40 bg-moderate/5' : 'border-line',
            )}
          >
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={challenge.unresolved ? 'warn' : 'muted'}>
                {challenge.challenge_type_label}
              </Badge>
              {challenge.unresolved ? (
                <span className="text-2xs text-moderate">
                  unresolved on the available evidence
                </span>
              ) : null}
              {challenge.on_demand ? (
                <span className="text-2xs text-ink-subtle">requested by analyst</span>
              ) : null}
            </div>
            <p className="mt-1.5 text-2xs leading-relaxed text-ink-muted">{challenge.argument}</p>
            {challenge.suggested_revision ? (
              <p className="mt-1.5 text-2xs leading-relaxed text-ink">
                <span className="font-semibold">Suggested revision: </span>
                {challenge.suggested_revision}
              </p>
            ) : null}
            {challenge.counter_evidence_ids.length > 0 ? (
              <p className="mt-1.5 text-2xs text-ink-subtle">
                Counter-evidence:{' '}
                {challenge.counter_evidence_ids.map((id) => (
                  <Mono key={id} className="mr-1">
                    {id}
                  </Mono>
                ))}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Overrides always require a rationale. An unexplained override is worthless in
 * an audit, so the requirement is enforced in the form as well as the API.
 */
function OverrideForm({
  label,
  options,
  current,
  aiValue,
  busy,
  onCancel,
  onSubmit,
}: {
  label: string;
  options: readonly string[] | null;
  current: string;
  aiValue: string;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (value: string, rationale: string) => void;
}) {
  const [value, setValue] = useState(options ? current : 'false_positive');
  const [rationale, setRationale] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const valid = rationale.trim().length >= 10 && (!options || value !== current);

  return (
    <div className="mt-4 rounded border border-accent/30 bg-accent-soft/40 px-4 py-3.5">
      <p className="text-2xs font-semibold uppercase tracking-[0.08em] text-ink-subtle">
        {label}
      </p>
      <p className="mt-1 text-2xs text-ink-muted">
        The system recommended <span className="font-semibold">{titleCase(aiValue)}</span>. Both
        values are kept on the record.
      </p>

      {options ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {options.map((option) => (
            <button
              key={option}
              onClick={() => setValue(option)}
              className={clsx(
                'rounded border px-2 py-1 text-2xs font-medium transition-colors',
                value === option
                  ? 'border-accent bg-accent text-white'
                  : 'border-line bg-surface text-ink-muted hover:border-line-strong hover:text-ink',
              )}
            >
              {titleCase(option)}
            </button>
          ))}
        </div>
      ) : null}

      <textarea
        ref={textareaRef}
        value={rationale}
        onChange={(event) => setRationale(event.target.value)}
        rows={3}
        placeholder="Why? This is recorded in the audit trail and appears in the report."
        className="mt-3 w-full rounded border border-line bg-surface px-3 py-2 text-xs text-ink placeholder:text-ink-subtle focus:border-accent"
      />
      <p className="mt-1 text-2xs text-ink-subtle">
        {rationale.trim().length < 10
          ? `A rationale of at least 10 characters is required (${rationale.trim().length}/10).`
          : 'Recorded alongside the original AI recommendation.'}
      </p>

      <div className="mt-3 flex gap-2">
        <Button
          size="sm"
          variant="primary"
          disabled={!valid}
          loading={busy}
          onClick={() => onSubmit(value, rationale)}
        >
          Save and recompute rating
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
