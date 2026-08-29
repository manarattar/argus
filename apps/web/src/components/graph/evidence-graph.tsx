'use client';

import clsx from 'clsx';
import { useMemo, useState } from 'react';

import { Badge, Card, CardHeader, Mono, SectionLabel } from '@/components/ui/primitives';
import { titleCase } from '@/lib/format';
import type { EvidenceGraphData, GraphNode } from '@/lib/types';

/**
 * The evidence graph.
 *
 * Built as a layered DAG rather than a force-directed cloud. Force layouts look
 * impressive in a screenshot and are close to useless for this job: the reader's
 * question is "where did this rating come from?", which is a directional
 * question, and a left-to-right flow answers it directly.
 *
 * Columns follow the actual dependency order of the pipeline:
 *
 *     document -> evidence -> challenge -> risk -> policy -> assessment
 *
 * Clicking any node highlights its complete lineage and dims everything else,
 * which turns "trace this rating to a page in a PDF" into one click.
 *
 * Rendered as plain SVG rather than through a graph library: the layout rules
 * are specific to this shape, and owning them means the diagram stays legible
 * at the sizes the product actually uses.
 */

const COLUMNS: GraphNode['kind'][] = [
  'document',
  'evidence',
  'challenge',
  'risk',
  'policy',
  'assessment',
];

const COLUMN_LABELS: Record<GraphNode['kind'], string> = {
  document: 'Source documents',
  evidence: 'Grounded evidence',
  challenge: 'Challenges',
  risk: 'Risk findings',
  policy: 'Policy clauses',
  assessment: 'Assessment',
};

const NODE_STYLE: Record<GraphNode['kind'], { fill: string; stroke: string; text: string }> = {
  document: { fill: 'fill-raised', stroke: 'stroke-line-strong', text: 'fill-ink' },
  evidence: { fill: 'fill-surface', stroke: 'stroke-accent/50', text: 'fill-ink' },
  challenge: { fill: 'fill-moderate/10', stroke: 'stroke-moderate/60', text: 'fill-ink' },
  risk: { fill: 'fill-surface', stroke: 'stroke-line-strong', text: 'fill-ink' },
  policy: { fill: 'fill-accent-soft', stroke: 'stroke-accent/40', text: 'fill-ink' },
  assessment: { fill: 'fill-surface', stroke: 'stroke-line-strong', text: 'fill-ink' },
};

const RELATION_STYLE: Record<string, { stroke: string; dash?: string; label: string }> = {
  supports: { stroke: 'stroke-accent/45', label: 'supports' },
  contradicts: { stroke: 'stroke-moderate', dash: '4 3', label: 'contradicts' },
  derived_from: { stroke: 'stroke-line-strong', label: 'derived from' },
  triggers: { stroke: 'stroke-accent/35', dash: '2 3', label: 'triggers' },
  challenges: { stroke: 'stroke-moderate/70', dash: '4 3', label: 'challenges' },
  rolls_up_to: { stroke: 'stroke-line-strong', label: 'rolls up to' },
};

const NODE_WIDTH = 168;
const NODE_HEIGHT = 46;
const COLUMN_GAP = 92;
const ROW_GAP = 14;
const PADDING = 28;

interface Positioned {
  node: GraphNode;
  x: number;
  y: number;
  column: number;
}

export function EvidenceGraph({ data }: { data: EvidenceGraphData }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  const layout = useMemo(() => {
    const byColumn = COLUMNS.map((kind) => data.nodes.filter((n) => n.kind === kind));
    const tallest = Math.max(1, ...byColumn.map((column) => column.length));
    const height = PADDING * 2 + tallest * (NODE_HEIGHT + ROW_GAP) + 26;
    const width = PADDING * 2 + COLUMNS.length * NODE_WIDTH + (COLUMNS.length - 1) * COLUMN_GAP;

    const positioned: Positioned[] = [];
    byColumn.forEach((column, columnIndex) => {
      const columnHeight = column.length * (NODE_HEIGHT + ROW_GAP) - ROW_GAP;
      const startY = PADDING + 26 + (height - PADDING * 2 - 26 - columnHeight) / 2;
      column.forEach((node, rowIndex) => {
        positioned.push({
          node,
          column: columnIndex,
          x: PADDING + columnIndex * (NODE_WIDTH + COLUMN_GAP),
          y: startY + rowIndex * (NODE_HEIGHT + ROW_GAP),
        });
      });
    });

    return { positioned, width, height };
  }, [data.nodes]);

  const positionById = useMemo(
    () => new Map(layout.positioned.map((item) => [item.node.id, item])),
    [layout.positioned],
  );

  /** Every node and edge reachable from the focused node, in either direction. */
  const lineage = useMemo(() => {
    const focus = selected ?? hovered;
    if (!focus) return null;

    const nodes = new Set<string>([focus]);
    const edges = new Set<string>();
    let frontier = [focus];

    // Walk upstream and downstream until nothing new is reached, so selecting a
    // risk shows its evidence *and* the documents behind that evidence.
    while (frontier.length) {
      const next: string[] = [];
      for (const id of frontier) {
        for (const [index, edge] of data.edges.entries()) {
          if (edge.source === id && !nodes.has(edge.target)) {
            nodes.add(edge.target);
            next.push(edge.target);
          }
          if (edge.target === id && !nodes.has(edge.source)) {
            nodes.add(edge.source);
            next.push(edge.source);
          }
          if (edge.source === id || edge.target === id) {
            edges.add(String(index));
          }
        }
      }
      frontier = next;
    }
    return { nodes, edges };
  }, [selected, hovered, data.edges]);

  const selectedNode = selected ? data.nodes.find((n) => n.id === selected) : null;

  return (
    <div className="grid gap-5 xl:grid-cols-4">
      <Card className="xl:col-span-3" padded={false}>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <div>
            <h2 className="text-sm font-semibold text-ink">Decision lineage</h2>
            <p className="mt-0.5 text-xs text-ink-muted">
              Click any node to trace its full lineage. Click again to clear.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {COLUMNS.map((kind) => (
              <Badge key={kind} tone="muted">
                {data.counts[kind] ?? 0} {COLUMN_LABELS[kind].toLowerCase()}
              </Badge>
            ))}
          </div>
        </div>

        <div className="scroll-slim overflow-x-auto p-4">
          <svg
            viewBox={`0 0 ${layout.width} ${layout.height}`}
            width={layout.width}
            height={layout.height}
            className="max-w-none"
            role="img"
            aria-label="Evidence lineage graph"
          >
            {/* Column headings */}
            {COLUMNS.map((kind, index) => (
              <text
                key={kind}
                x={PADDING + index * (NODE_WIDTH + COLUMN_GAP) + NODE_WIDTH / 2}
                y={PADDING}
                textAnchor="middle"
                className="fill-ink-subtle text-[9px] font-semibold uppercase tracking-[0.12em]"
              >
                {COLUMN_LABELS[kind]}
              </text>
            ))}

            {/* Edges first, so nodes always sit on top */}
            <g>
              {data.edges.map((edge, index) => {
                const from = positionById.get(edge.source);
                const to = positionById.get(edge.target);
                if (!from || !to) return null;

                const style = RELATION_STYLE[edge.relation] ?? RELATION_STYLE.supports!;
                const active = lineage ? lineage.edges.has(String(index)) : true;

                const x1 = from.x + NODE_WIDTH;
                const y1 = from.y + NODE_HEIGHT / 2;
                const x2 = to.x;
                const y2 = to.y + NODE_HEIGHT / 2;
                const midX = (x1 + x2) / 2;

                return (
                  <path
                    key={`${edge.source}-${edge.target}-${index}`}
                    d={`M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`}
                    fill="none"
                    strokeWidth={active && lineage ? 1.6 : 1}
                    strokeDasharray={style.dash}
                    className={clsx(
                      style.stroke,
                      'transition-opacity',
                      lineage && !active ? 'opacity-10' : 'opacity-70',
                    )}
                  />
                );
              })}
            </g>

            {/* Nodes */}
            <g>
              {layout.positioned.map(({ node, x, y }) => {
                const active = lineage ? lineage.nodes.has(node.id) : true;
                const style = NODE_STYLE[node.kind];
                const isSelected = selected === node.id;

                return (
                  <g
                    key={node.id}
                    transform={`translate(${x}, ${y})`}
                    className={clsx(
                      'cursor-pointer transition-opacity',
                      lineage && !active ? 'opacity-15' : 'opacity-100',
                    )}
                    onClick={() => setSelected(isSelected ? null : node.id)}
                    onMouseEnter={() => setHovered(node.id)}
                    onMouseLeave={() => setHovered(null)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        setSelected(isSelected ? null : node.id);
                      }
                    }}
                  >
                    <title>{`${node.label}${node.sublabel ? ` — ${node.sublabel}` : ''}`}</title>
                    <rect
                      width={NODE_WIDTH}
                      height={NODE_HEIGHT}
                      rx={5}
                      className={clsx(
                        style.fill,
                        isSelected ? 'stroke-accent' : style.stroke,
                        'transition-all',
                      )}
                      strokeWidth={isSelected ? 2 : 1}
                    />
                    {node.kind === 'risk' || node.kind === 'assessment' ? (
                      <rect
                        width={3}
                        height={NODE_HEIGHT}
                        rx={1.5}
                        className={riskFill(node)}
                      />
                    ) : null}
                    <text
                      x={10}
                      y={18}
                      className={clsx(style.text, 'text-[10px] font-semibold')}
                    >
                      {clip(node.label, 24)}
                    </text>
                    <text x={10} y={32} className="fill-ink-subtle text-[9px]">
                      {clip(node.sublabel, 28)}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>
        </div>

        <div className="flex flex-wrap items-center gap-4 border-t border-line px-5 py-3">
          {Object.entries(RELATION_STYLE).map(([relation, style]) => (
            <span key={relation} className="flex items-center gap-1.5 text-2xs text-ink-muted">
              <svg width="22" height="6" aria-hidden>
                <line
                  x1="0"
                  y1="3"
                  x2="22"
                  y2="3"
                  strokeWidth="1.6"
                  strokeDasharray={style.dash}
                  className={style.stroke}
                />
              </svg>
              {style.label}
            </span>
          ))}
        </div>
      </Card>

      <div className="space-y-5">
        <Card>
          <CardHeader
            title={selectedNode ? 'Selected node' : 'Nothing selected'}
            description={
              selectedNode
                ? undefined
                : 'Click a node in the graph to inspect it and highlight its lineage.'
            }
          />
          {selectedNode ? (
            <NodeDetail node={selectedNode} />
          ) : (
            <p className="mt-3 text-xs leading-relaxed text-ink-muted">
              Start from a risk finding to see the evidence behind it, the documents that
              evidence came from, the policy clauses it triggers and any challenge raised
              against it.
            </p>
          )}
        </Card>

        <Card>
          <CardHeader title="How to read this" />
          <ul className="mt-3 space-y-2 text-2xs leading-relaxed text-ink-muted">
            <li>· Flow runs left to right, following the pipeline&apos;s real dependency order.</li>
            <li>· Every edge is a stored relationship, not an inferred one - citations were recorded as identifiers, so this graph is a query rather than a reconstruction.</li>
            <li>· Dashed lines carry disagreement: contradicting evidence and challenges.</li>
            <li>· A risk with no incoming evidence edge is a finding whose citations did not survive grounding verification.</li>
          </ul>
        </Card>
      </div>
    </div>
  );
}

function NodeDetail({ node }: { node: GraphNode }) {
  const meta = node.meta ?? {};
  const entries = Object.entries(meta).filter(
    ([, value]) => value !== '' && value !== null && value !== undefined,
  );

  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="accent">{titleCase(node.kind)}</Badge>
        <Mono>{node.id}</Mono>
      </div>
      <p className="mt-2.5 text-sm font-medium text-ink">{node.label}</p>
      {node.sublabel ? (
        <p className="mt-1 text-xs leading-relaxed text-ink-muted">{node.sublabel}</p>
      ) : null}

      {entries.length > 0 ? (
        <div className="mt-4">
          <SectionLabel>Detail</SectionLabel>
          <dl className="space-y-1.5">
            {entries.map(([key, value]) => (
              <div key={key} className="flex gap-3 border-b border-line pb-1.5 last:border-0">
                <dt className="w-28 shrink-0 text-2xs text-ink-subtle">{titleCase(key)}</dt>
                <dd className="min-w-0 flex-1 text-2xs leading-relaxed text-ink">
                  {typeof value === 'number'
                    ? value.toFixed(value % 1 === 0 ? 0 : 2)
                    : String(value)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
    </div>
  );
}

function riskFill(node: GraphNode): string {
  const level =
    (node.meta?.level as string | undefined) ??
    severityToLevel(node.meta?.severity as string | undefined);
  return (
    {
      low: 'fill-low',
      moderate: 'fill-moderate',
      elevated: 'fill-elevated',
      high: 'fill-high',
    }[level ?? ''] ?? 'fill-line-strong'
  );
}

function severityToLevel(severity?: string): string | undefined {
  return {
    negligible: 'low',
    minor: 'low',
    moderate: 'moderate',
    major: 'elevated',
    severe: 'high',
  }[severity ?? ''];
}

function clip(text: string, limit: number): string {
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}
