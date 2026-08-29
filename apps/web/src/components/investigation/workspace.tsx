'use client';

import clsx from 'clsx';
import { useCallback, useState } from 'react';

import { AssessmentPanel } from './assessment';
import { AskPanel } from './ask';
import { AuditPanel } from './audit';
import { EvidencePanel } from './evidence';
import { FindingsPanel } from './findings';
import { PolicyPanel } from './policy';
import { ReportPanel } from './report';
import { ReviewGate } from './review';
import { TracePanel } from './trace';

import { LinkButton } from '@/components/ui/button';
import { Badge, Card, RiskBadge, StrengthBadge } from '@/components/ui/primitives';
import { formatCurrency, formatDuration, formatPercent } from '@/lib/format';
import type { AuditEvent, InvestigationDetail } from '@/lib/types';

type TabKey =
  | 'assessment'
  | 'findings'
  | 'evidence'
  | 'policy'
  | 'trace'
  | 'ask'
  | 'report'
  | 'audit';

/**
 * The analyst workspace.
 *
 * State lives here rather than in each panel because a single edit - changing a
 * severity, marking a false positive - changes the rating, the score factors and
 * the escalation state at once. Holding the investigation in one place means
 * every panel updates from the same response, and the analyst sees the
 * consequence of their edit immediately rather than after a reload.
 */
export function InvestigationWorkspace({
  caseId,
  initial,
  auditEvents,
  suggestedQuestions,
}: {
  caseId: string;
  initial: InvestigationDetail;
  auditEvents: AuditEvent[];
  suggestedQuestions: string[];
}) {
  const [investigation, setInvestigation] = useState(initial);
  const [tab, setTab] = useState<TabKey>('assessment');
  const [focusRisk, setFocusRisk] = useState<string | null>(null);

  const patch = useCallback((next: Partial<InvestigationDetail>) => {
    setInvestigation((current) => ({ ...current, ...next }));
  }, []);

  const openFinding = useCallback((riskId: string) => {
    setFocusRisk(riskId);
    setTab('findings');
  }, []);

  const activeFindings = investigation.risks.filter((r) => !r.is_false_positive);
  const unresolvedChallenges = investigation.challenges.filter((c) => c.unresolved).length;
  const weakFindings = activeFindings.filter((r) =>
    ['weak', 'insufficient'].includes(r.evidence_strength),
  ).length;

  const tabs: { key: TabKey; label: string; count?: number; alert?: boolean }[] = [
    { key: 'assessment', label: 'Assessment' },
    { key: 'findings', label: 'Findings', count: activeFindings.length },
    { key: 'evidence', label: 'Evidence', count: investigation.evidence.length },
    { key: 'policy', label: 'Policy', count: investigation.policy_matches.length },
    { key: 'trace', label: 'Trace', count: investigation.steps.length, alert: investigation.has_errors },
    { key: 'ask', label: 'Ask ARGUS' },
    { key: 'report', label: 'Report' },
    { key: 'audit', label: 'Audit', count: auditEvents.length },
  ];

  return (
    <div className="space-y-5">
      {/* Assessment header: the one thing always on screen. */}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="min-w-0">
            <p className="mb-2 text-2xs font-semibold uppercase tracking-[0.12em] text-ink-subtle">
              Provisional assessment
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <RiskBadge
                level={investigation.overall_level}
                score={investigation.overall_score}
                size="lg"
              />
              <StrengthBadge
                strength={investigation.evidence_strength}
                rationale="Evidence strength across the findings driving this rating."
              />
              {investigation.demo_mode ? (
                <Badge tone="muted" title="Model responses were replayed from recordings.">
                  replayed responses
                </Badge>
              ) : null}
              {investigation.status === 'awaiting_human_review' ? (
                <Badge tone="warn">Awaiting your decision</Badge>
              ) : null}
              {investigation.status === 'completed' ? <Badge tone="ok">Reviewed</Badge> : null}
              {investigation.status === 'failed' ? <Badge tone="alert">Run failed</Badge> : null}
            </div>
            <p className="mt-2.5 max-w-2xl text-xs leading-relaxed text-ink-muted">
              Computed by the scoring engine from {activeFindings.length} finding
              {activeFindings.length === 1 ? '' : 's'}, {investigation.policy_matches.length} policy
              match{investigation.policy_matches.length === 1 ? '' : 'es'} and{' '}
              {investigation.evidence.length} grounded evidence item
              {investigation.evidence.length === 1 ? '' : 's'}. Not generated as free text.
            </p>
          </div>

          <dl className="grid shrink-0 grid-cols-2 gap-x-8 gap-y-3 text-xs sm:grid-cols-4">
            <HeaderStat label="Duration" value={formatDuration(investigation.duration_ms)} />
            <HeaderStat
              label="Retrieval quality"
              value={formatPercent(investigation.retrieval_quality, 0)}
            />
            <HeaderStat
              label="Weakly evidenced"
              value={String(weakFindings)}
              tone={weakFindings > 0 ? 'warn' : undefined}
            />
            <HeaderStat
              label="Unresolved challenges"
              value={String(unresolvedChallenges)}
              tone={unresolvedChallenges > 0 ? 'warn' : undefined}
            />
            <HeaderStat
              label="Est. cost"
              value={formatCurrency(investigation.estimated_cost_usd, 4)}
            />
            <HeaderStat
              label="Tokens"
              value={`${investigation.tokens.input + investigation.tokens.output}`}
            />
            <HeaderStat label="Model" value={investigation.model_name || '—'} />
            <HeaderStat
              label="Steps failed"
              value={String(investigation.errors.length)}
              tone={investigation.errors.length > 0 ? 'alert' : undefined}
            />
          </dl>
        </div>

        {investigation.escalation_reasons.length > 0 ? (
          <div className="mt-4 rounded border border-high/30 bg-high/5 px-4 py-3">
            <p className="text-xs font-semibold text-high">
              Mandatory escalation — this assessment cannot be approved directly
            </p>
            <ul className="mt-1.5 space-y-1 text-xs leading-relaxed text-ink-muted">
              {investigation.escalation_reasons.map((reason) => (
                <li key={reason}>· {reason}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {investigation.errors.length > 0 ? (
          <div className="mt-4 rounded border border-high/30 bg-high/5 px-4 py-3">
            <p className="text-xs font-semibold text-high">
              {investigation.errors.length} step
              {investigation.errors.length === 1 ? '' : 's'} failed during this investigation
            </p>
            <ul className="mt-1.5 space-y-1 font-mono text-2xs leading-relaxed text-ink-muted">
              {investigation.errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
            <p className="mt-2 text-2xs text-ink-muted">
              Results below reflect only the steps that completed. Nothing has been substituted
              for the missing output.
            </p>
          </div>
        ) : null}
      </Card>

      <ReviewGate investigation={investigation} onUpdate={patch} />

      {/* Tabs */}
      <div className="border-b border-line">
        <nav className="-mb-px flex flex-wrap gap-1" role="tablist" aria-label="Investigation views">
          {tabs.map((item) => (
            <button
              key={item.key}
              role="tab"
              aria-selected={tab === item.key}
              onClick={() => setTab(item.key)}
              className={clsx(
                'flex items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-medium transition-colors',
                tab === item.key
                  ? 'border-accent text-accent'
                  : 'border-transparent text-ink-muted hover:border-line-strong hover:text-ink',
              )}
            >
              {item.label}
              {item.count !== undefined ? (
                <span
                  className={clsx(
                    'tabular rounded px-1 py-px text-2xs',
                    tab === item.key ? 'bg-accent-soft' : 'bg-raised',
                  )}
                >
                  {item.count}
                </span>
              ) : null}
              {item.alert ? <span className="h-1.5 w-1.5 rounded-full bg-high" /> : null}
            </button>
          ))}
        </nav>
      </div>

      <div className="animate-fade-up">
        {tab === 'assessment' ? (
          <AssessmentPanel investigation={investigation} onOpenFinding={openFinding} />
        ) : null}
        {tab === 'findings' ? (
          <FindingsPanel
            investigation={investigation}
            onUpdate={patch}
            focusRisk={focusRisk}
            onFocusHandled={() => setFocusRisk(null)}
          />
        ) : null}
        {tab === 'evidence' ? <EvidencePanel investigation={investigation} /> : null}
        {tab === 'policy' ? (
          <PolicyPanel investigation={investigation} onOpenFinding={openFinding} />
        ) : null}
        {tab === 'trace' ? <TracePanel investigation={investigation} /> : null}
        {tab === 'ask' ? (
          <AskPanel investigation={investigation} suggestedQuestions={suggestedQuestions} />
        ) : null}
        {tab === 'report' ? <ReportPanel caseId={caseId} investigation={investigation} /> : null}
        {tab === 'audit' ? <AuditPanel events={auditEvents} /> : null}
      </div>

      <div className="flex flex-wrap gap-2 pt-1">
        <LinkButton href={`/graph?investigation=${investigation.id}`} size="sm">
          Open in Evidence Graph
        </LinkButton>
        <LinkButton href={`/scenario?investigation=${investigation.id}`} size="sm">
          Open in Scenario Lab
        </LinkButton>
      </div>
    </div>
  );
}

function HeaderStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: 'warn' | 'alert';
}) {
  return (
    <div>
      <dt className="text-2xs uppercase tracking-[0.08em] text-ink-subtle">{label}</dt>
      <dd
        className={clsx(
          'tabular mt-0.5 font-medium',
          tone === 'alert' ? 'text-high' : tone === 'warn' ? 'text-moderate' : 'text-ink',
        )}
      >
        {value}
      </dd>
    </div>
  );
}
