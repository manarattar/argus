'use client';

import { useMemo, useState } from 'react';

import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  Metric,
  MetricGrid,
  Mono,
  Table,
  Td,
  Th,
} from '@/components/ui/primitives';
import { formatPercent, titleCase } from '@/lib/format';
import type { InvestigationDetail } from '@/lib/types';

/**
 * The evidence base, including what was thrown away.
 *
 * Showing rejected evidence is a deliberate choice. A pipeline that silently
 * drops ungrounded output looks cleaner than it is; showing the rejects is how
 * a reviewer can see the grounding control doing work.
 */
export function EvidencePanel({ investigation }: { investigation: InvestigationDetail }) {
  const [category, setCategory] = useState<string>('all');
  const [kind, setKind] = useState<'all' | 'fact' | 'interpretation'>('all');

  const categories = useMemo(
    () => Array.from(new Set(investigation.evidence.map((e) => e.category))).sort(),
    [investigation.evidence],
  );

  const filtered = investigation.evidence.filter(
    (item) =>
      (category === 'all' || item.category === category) &&
      (kind === 'all' || item.kind === kind),
  );

  const facts = investigation.evidence.filter((e) => e.kind === 'fact').length;
  const meanGrounding = investigation.evidence.length
    ? investigation.evidence.reduce((sum, e) => sum + e.grounding_score, 0) /
      investigation.evidence.length
    : 0;
  const proposed = investigation.evidence.length + investigation.rejected_evidence.length;

  return (
    <div className="space-y-5">
      <Card>
        <MetricGrid columns={4}>
          <Metric
            label="Grounded evidence"
            value={investigation.evidence.length}
            footnote={`of ${proposed} extracted`}
            hint="Items whose quote was verified against stored source text."
          />
          <Metric
            label="Facts vs interpretations"
            value={`${facts} / ${investigation.evidence.length - facts}`}
            footnote="Stated vs inferred"
            hint="Only facts count toward evidence coverage."
          />
          <Metric
            label="Mean grounding score"
            value={formatPercent(meanGrounding, 0)}
            footnote="Verbatim match quality"
          />
          <Metric
            label="Rejected by control"
            value={investigation.rejected_evidence.length}
            tone={investigation.rejected_evidence.length > 0 ? 'alert' : 'default'}
            footnote="Discarded before analysis"
          />
        </MetricGrid>
      </Card>

      <Card>
        <CardHeader
          title="Evidence base"
          description="Every item was re-matched against its source chunk before any agent could cite it."
          actions={
            <div className="flex gap-2">
              <select
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                aria-label="Filter by category"
                className="rounded border border-line bg-surface px-2 py-1 text-2xs text-ink"
              >
                <option value="all">All categories</option>
                {categories.map((value) => (
                  <option key={value} value={value}>
                    {titleCase(value)}
                  </option>
                ))}
              </select>
              <select
                value={kind}
                onChange={(event) => setKind(event.target.value as typeof kind)}
                aria-label="Filter by kind"
                className="rounded border border-line bg-surface px-2 py-1 text-2xs text-ink"
              >
                <option value="all">Facts and interpretations</option>
                <option value="fact">Facts only</option>
                <option value="interpretation">Interpretations only</option>
              </select>
            </div>
          }
        />

        <div className="mt-4">
          {filtered.length === 0 ? (
            <EmptyState
              title="No evidence matches these filters"
              description="Clear the filters to see the full evidence base."
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>ID</Th>
                  <Th>Statement and source quote</Th>
                  <Th>Category</Th>
                  <Th>Source</Th>
                  <Th align="right">Grounding</Th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => (
                  <tr key={item.evidence_id}>
                    <Td>
                      <Mono>{item.evidence_id}</Mono>
                    </Td>
                    <Td>
                      <p className="text-ink">{item.statement}</p>
                      <p className="mt-1 border-l border-line pl-2 text-2xs italic leading-relaxed text-ink-muted">
                        “{item.quote}”
                      </p>
                    </Td>
                    <Td>
                      <div className="flex flex-col gap-1">
                        <Badge tone="muted">{item.category_label}</Badge>
                        {item.kind === 'interpretation' ? (
                          <Badge tone="warn" title="The model's reading, not a stated fact.">
                            interpretation
                          </Badge>
                        ) : null}
                      </div>
                    </Td>
                    <Td className="whitespace-nowrap text-ink-muted">
                      {item.document_name}
                      <span className="mt-0.5 block text-2xs text-ink-subtle">
                        {item.section_reference}
                      </span>
                    </Td>
                    <Td align="right">
                      <span
                        className={
                          item.grounding_score >= 0.99 ? 'text-low' : 'text-ink-muted'
                        }
                        title={
                          item.grounding_score >= 0.99
                            ? 'Quote found verbatim in the cited chunk.'
                            : 'Quote matched after whitespace and punctuation normalisation.'
                        }
                      >
                        {formatPercent(item.grounding_score, 0)}
                      </span>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </div>
      </Card>

      {investigation.rejected_evidence.length > 0 ? (
        <Card>
          <CardHeader
            title="Evidence rejected by the grounding control"
            description="Extracted by the model, then discarded because the quote could not be located in any source document. Retained so the control is auditable."
          />
          <div className="mt-4">
            <Table>
              <thead>
                <tr>
                  <Th>ID</Th>
                  <Th>Statement</Th>
                  <Th>Reason</Th>
                  <Th align="right">Best match</Th>
                </tr>
              </thead>
              <tbody>
                {investigation.rejected_evidence.map((item) => (
                  <tr key={item.evidence_id}>
                    <Td>
                      <Mono>{item.evidence_id}</Mono>
                    </Td>
                    <Td className="text-ink-muted line-through">{item.statement}</Td>
                    <Td className="text-ink-muted">{item.reason}</Td>
                    <Td align="right" className="text-high">
                      {formatPercent(item.grounding_score, 0)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
