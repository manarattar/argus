'use client';

import clsx from 'clsx';

import {
  Bar,
  Card,
  CardHeader,
  CoverageBadge,
  EmptyState,
  RiskBadge,
  SectionLabel,
} from '@/components/ui/primitives';
import { titleCase } from '@/lib/format';
import type { InvestigationDetail } from '@/lib/types';

/**
 * The assessment view answers "why this rating?" before it answers anything
 * else. Score factors come first, with their arithmetic visible, because the
 * central claim of the product is that the number is explainable.
 */
export function AssessmentPanel({
  investigation,
  onOpenFinding,
}: {
  investigation: InvestigationDetail;
  onOpenFinding: (riskId: string) => void;
}) {
  const narrative = investigation.narrative ?? {};
  const factors = investigation.score_factors ?? [];
  const maxContribution = Math.max(1, ...factors.map((f) => Math.abs(f.contribution)));
  const categories = Object.entries(investigation.category_levels ?? {});

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <div className="space-y-5 lg:col-span-2">
        <Card>
          <CardHeader
            title="Executive summary"
            description="Written by the synthesis agent to explain a rating it did not decide."
          />
          {narrative.executive_summary ? (
            <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-ink-muted">
              {narrative.executive_summary}
            </p>
          ) : (
            <div className="mt-3">
              <EmptyState
                title="No narrative was produced"
                description="The synthesis step did not complete. The rating above still stands — it was computed deterministically from the findings and does not depend on this step."
              />
            </div>
          )}

          {narrative.key_judgements && narrative.key_judgements.length > 0 ? (
            <div className="mt-5">
              <SectionLabel>Key judgements</SectionLabel>
              <ul className="space-y-2">
                {narrative.key_judgements.map((judgement) => (
                  <li key={judgement} className="flex gap-2.5 text-xs leading-relaxed text-ink-muted">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                    {judgement}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </Card>

        <Card>
          <CardHeader
            title="How this rating was calculated"
            description="Every point is attributable to a named factor. The model supplies the judgements; the institution owns the arithmetic."
          />
          <div className="mt-4 space-y-3.5">
            {factors.map((factor) => (
              <div key={factor.key}>
                <div className="flex items-baseline justify-between gap-4">
                  <p className="text-xs font-medium text-ink">{factor.label}</p>
                  <p
                    className={clsx(
                      'tabular shrink-0 text-xs font-semibold',
                      factor.direction === 'increases'
                        ? 'text-high'
                        : factor.direction === 'decreases'
                          ? 'text-low'
                          : 'text-ink-subtle',
                    )}
                  >
                    {factor.contribution > 0 ? '+' : ''}
                    {factor.contribution.toFixed(1)}
                  </p>
                </div>
                <Bar
                  value={factor.contribution}
                  max={maxContribution}
                  tone={
                    factor.direction === 'increases'
                      ? 'negative'
                      : factor.direction === 'decreases'
                        ? 'positive'
                        : 'muted'
                  }
                  className="mt-1.5"
                />
                <p className="mt-1.5 text-2xs leading-relaxed text-ink-muted">{factor.detail}</p>
              </div>
            ))}
            <div className="flex items-baseline justify-between border-t border-line pt-3">
              <p className="text-xs font-semibold text-ink">Composite score</p>
              <p className="tabular text-sm font-semibold text-ink">
                {investigation.overall_score.toFixed(1)} / 100
              </p>
            </div>
          </div>
        </Card>

        {narrative.mind_changers && narrative.mind_changers.length > 0 ? (
          <Card>
            <CardHeader
              title="What would change this assessment"
              description="The specific evidence that would move each finding, in either direction."
            />
            <div className="mt-4 space-y-4">
              {narrative.mind_changers.map((changer) => {
                const finding = investigation.risks.find((r) => r.risk_id === changer.risk_id);
                return (
                  <div key={changer.risk_id} className="border-l-2 border-line pl-3.5">
                    <button
                      onClick={() => onOpenFinding(changer.risk_id)}
                      className="text-left text-xs font-medium text-ink hover:text-accent"
                    >
                      {finding?.title ?? changer.risk_id}
                    </button>
                    {changer.would_increase ? (
                      <p className="mt-1.5 text-2xs leading-relaxed text-ink-muted">
                        <span className="font-semibold text-high">Would raise it: </span>
                        {changer.would_increase}
                      </p>
                    ) : null}
                    {changer.would_decrease ? (
                      <p className="mt-1 text-2xs leading-relaxed text-ink-muted">
                        <span className="font-semibold text-low">Would lower it: </span>
                        {changer.would_decrease}
                      </p>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </Card>
        ) : null}
      </div>

      <div className="space-y-5">
        {categories.length > 0 ? (
          <Card>
            <CardHeader title="Rating by category" />
            <ul className="mt-3 space-y-2">
              {categories
                .sort(([, a], [, b]) => (b > a ? 1 : -1))
                .map(([category, level]) => (
                  <li
                    key={category}
                    className="flex items-center justify-between gap-3 border-b border-line pb-2 last:border-0 last:pb-0"
                  >
                    <span className="text-xs text-ink-muted">{titleCase(category)}</span>
                    <RiskBadge level={level} />
                  </li>
                ))}
            </ul>
          </Card>
        ) : null}

        <Card>
          <CardHeader
            title="Investigation completeness"
            description="Measured against what this review type expects, not against what the model happened to find."
          />
          <ul className="mt-3 space-y-2.5">
            {(investigation.coverage ?? []).map((item) => (
              <li key={item.category} className="border-b border-line pb-2.5 last:border-0 last:pb-0">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-xs font-medium text-ink">
                    {item.category_label ?? titleCase(item.category)}
                  </p>
                  <CoverageBadge status={item.status} />
                </div>
                <p className="mt-1 text-2xs leading-relaxed text-ink-subtle">{item.expected}</p>
                {item.note ? (
                  <p className="mt-1 text-2xs leading-relaxed text-ink-muted">{item.note}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </Card>

        {narrative.limitations && narrative.limitations.length > 0 ? (
          <Card>
            <CardHeader
              title="Limitations"
              description="What this assessment cannot tell you."
            />
            <ul className="mt-3 space-y-2">
              {narrative.limitations.map((limitation) => (
                <li key={limitation} className="flex gap-2.5 text-2xs leading-relaxed text-ink-muted">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-moderate" />
                  {limitation}
                </li>
              ))}
            </ul>
          </Card>
        ) : null}

        {narrative.recommended_followup && narrative.recommended_followup.length > 0 ? (
          <Card>
            <CardHeader title="Recommended follow-up" />
            <ul className="mt-3 space-y-2">
              {narrative.recommended_followup.map((item) => (
                <li key={item} className="flex gap-2.5 text-2xs leading-relaxed text-ink-muted">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                  {item}
                </li>
              ))}
            </ul>
          </Card>
        ) : null}

        {investigation.integrity?.summary ? (
          <Card>
            <CardHeader
              title="Citation integrity"
              description="Result of re-checking every citation against stored source text."
            />
            <p className="mt-2.5 text-2xs leading-relaxed text-ink-muted">
              {String(investigation.integrity.summary)}
            </p>
            {investigation.rejected_evidence.length > 0 ? (
              <p className="mt-2 text-2xs text-ink-subtle">
                {investigation.rejected_evidence.length} extracted item
                {investigation.rejected_evidence.length === 1 ? '' : 's'} discarded before
                analysis. See the Evidence tab.
              </p>
            ) : null}
          </Card>
        ) : null}
      </div>
    </div>
  );
}
