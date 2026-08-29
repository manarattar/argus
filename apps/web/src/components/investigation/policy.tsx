'use client';

import {
  Card,
  CardHeader,
  EmptyState,
  Mono,
  Table,
  Td,
  Th,
  TriggerBadge,
} from '@/components/ui/primitives';
import type { InvestigationDetail } from '@/lib/types';

/**
 * Policy matches, grouped by clause rather than by finding.
 *
 * A reviewer asking "which parts of the framework does this counterparty
 * touch?" wants the clause view; the finding view is already on the Findings
 * tab.
 */
export function PolicyPanel({
  investigation,
  onOpenFinding,
}: {
  investigation: InvestigationDetail;
  onOpenFinding: (riskId: string) => void;
}) {
  if (investigation.policy_matches.length === 0) {
    return (
      <EmptyState
        title="No policy clauses were matched"
        description="Either the policy library returned nothing relevant, or the policy step did not complete. Check the Trace tab."
      />
    );
  }

  const byClause = new Map<string, typeof investigation.policy_matches>();
  for (const match of investigation.policy_matches) {
    const existing = byClause.get(match.clause_reference) ?? [];
    existing.push(match);
    byClause.set(match.clause_reference, existing);
  }

  const titleOf = (riskId: string) =>
    investigation.risks.find((r) => r.risk_id === riskId)?.title ?? riskId;

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title="Policy exposure"
          description="Clauses of the internal framework that the findings engage. Clause references are deterministic citation keys, not model-generated text."
        />
        <div className="mt-4">
          <Table>
            <thead>
              <tr>
                <Th>Clause</Th>
                <Th>Title</Th>
                <Th>Relationship</Th>
                <Th>Findings</Th>
              </tr>
            </thead>
            <tbody>
              {Array.from(byClause.entries()).map(([reference, matches]) => (
                <tr key={reference}>
                  <Td>
                    <Mono>{reference}</Mono>
                  </Td>
                  <Td className="text-ink">{matches[0]?.clause_title}</Td>
                  <Td>
                    <TriggerBadge trigger={matches[0]?.trigger_type ?? 'informational'} />
                  </Td>
                  <Td>
                    <div className="flex flex-col gap-1">
                      {matches.map((match) => (
                        <button
                          key={match.match_id}
                          onClick={() => onOpenFinding(match.risk_id)}
                          className="text-left text-2xs text-accent hover:underline"
                        >
                          {titleOf(match.risk_id)}
                        </button>
                      ))}
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      </Card>

      <div className="space-y-3">
        {investigation.policy_matches.map((match) => (
          <Card key={match.match_id}>
            <div className="flex flex-wrap items-center gap-2">
              <Mono>{match.clause_reference}</Mono>
              <h3 className="text-sm font-semibold text-ink">{match.clause_title}</h3>
              <TriggerBadge trigger={match.trigger_type} />
              <button
                onClick={() => onOpenFinding(match.risk_id)}
                className="ml-auto text-2xs text-accent hover:underline"
              >
                {titleOf(match.risk_id)}
              </button>
            </div>
            <p className="mt-2.5 text-xs leading-relaxed text-ink-muted">{match.relevance}</p>
            {match.threshold_assessment ? (
              <p className="mt-2 rounded border border-line bg-raised/50 px-3 py-2 text-2xs leading-relaxed text-ink">
                <span className="font-semibold">Threshold assessment: </span>
                {match.threshold_assessment}
              </p>
            ) : null}
            {match.sufficiency_caveat ? (
              <p className="mt-2 text-2xs italic leading-relaxed text-ink-subtle">
                {match.sufficiency_caveat}
              </p>
            ) : null}
          </Card>
        ))}
      </div>
    </div>
  );
}
