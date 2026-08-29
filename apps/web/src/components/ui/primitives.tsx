/**
 * The component vocabulary.
 *
 * Hand-built rather than pulled from a component library, for two reasons: the
 * set needed is small and specific, and an enterprise analytics interface lives
 * or dies on density and restraint - qualities that are easier to hold on to
 * when the primitives are yours.
 *
 * Every component here is presentational and server-safe.
 */

import clsx from 'clsx';
import type { ReactNode } from 'react';

import {
  coverageLabels,
  riskClasses,
  riskLevelOf,
  strengthClasses,
  triggerLabels,
  verificationLabels,
} from '@/lib/format';
import type { EvidenceStrength } from '@/lib/types';

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export function Card({
  children,
  className,
  padded = true,
  id,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
  id?: string;
}) {
  return (
    <section
      id={id}
      className={clsx(
        'rounded-lg border border-line bg-surface shadow-card',
        padded && 'p-5',
        className,
      )}
    >
      {children}
    </section>
  );
}

export function CardHeader({
  title,
  description,
  actions,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx('flex items-start justify-between gap-4', className)}>
      <div className="min-w-0">
        <h2 className="text-sm font-semibold tracking-tight text-ink">{title}</h2>
        {description ? (
          <p className="mt-1 text-xs leading-relaxed text-ink-muted">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="shrink-0">{actions}</div> : null}
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0 max-w-3xl">
        {eyebrow ? (
          <p className="mb-1.5 text-2xs font-semibold uppercase tracking-[0.14em] text-ink-subtle">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {description ? (
          <div className="mt-2 text-sm leading-relaxed text-ink-muted">{description}</div>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="mb-2 text-2xs font-semibold uppercase tracking-[0.12em] text-ink-subtle">
      {children}
    </p>
  );
}

// ---------------------------------------------------------------------------
// Badges
// ---------------------------------------------------------------------------

const toneClasses = {
  ok: 'border-low/30 bg-low/10 text-low',
  warn: 'border-moderate/30 bg-moderate/10 text-moderate',
  alert: 'border-high/30 bg-high/10 text-high',
  muted: 'border-line bg-raised text-ink-muted',
  accent: 'border-accent/25 bg-accent-soft text-accent',
} as const;

export type Tone = keyof typeof toneClasses;

export function Badge({
  children,
  tone = 'muted',
  className,
  title,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={clsx(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded border px-1.5 py-0.5 text-2xs font-medium',
        toneClasses[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** The product's most repeated element: a risk rating. */
export function RiskBadge({
  level,
  score,
  size = 'sm',
}: {
  level: string | null | undefined;
  score?: number;
  size?: 'sm' | 'lg';
}) {
  const risk = riskLevelOf(level);
  if (!risk) {
    return (
      <Badge tone="muted" title="No rating has been computed for this investigation.">
        Unrated
      </Badge>
    );
  }
  const classes = riskClasses[risk];
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-2 rounded border font-semibold',
        classes.bg,
        classes.border,
        classes.text,
        size === 'lg' ? 'px-2.5 py-1 text-sm' : 'px-1.5 py-0.5 text-2xs',
      )}
    >
      <span className={clsx('rounded-full', classes.dot, size === 'lg' ? 'h-2 w-2' : 'h-1.5 w-1.5')} />
      <span className="capitalize">{risk}</span>
      {score !== undefined ? (
        <span className="tabular font-normal opacity-70">{score.toFixed(0)}</span>
      ) : null}
    </span>
  );
}

/**
 * Evidence strength, with the reason attached.
 *
 * The rationale is always available on hover because a band without its
 * reasoning is exactly the kind of unexplained confidence signal this product
 * is designed to avoid.
 */
export function StrengthBadge({
  strength,
  rationale,
}: {
  strength: EvidenceStrength | '' | null | undefined;
  rationale?: string;
}) {
  if (!strength) return null;
  const label = `${strength.charAt(0).toUpperCase()}${strength.slice(1)} evidence`;
  return (
    <span
      title={rationale || label}
      className={clsx(
        'inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-2xs font-medium',
        strengthClasses[strength],
      )}
    >
      <EvidenceMeter strength={strength} />
      {label}
    </span>
  );
}

/** Four bars filled to the strength level - readable without colour. */
function EvidenceMeter({ strength }: { strength: EvidenceStrength }) {
  const filled = { strong: 4, moderate: 3, weak: 2, insufficient: 1 }[strength];
  return (
    <span className="flex items-end gap-px" aria-hidden>
      {[1, 2, 3, 4].map((bar) => (
        <span
          key={bar}
          className={clsx(
            'w-0.5 rounded-sm',
            bar <= filled ? 'bg-current' : 'bg-current opacity-25',
          )}
          style={{ height: `${3 + bar * 1.5}px` }}
        />
      ))}
    </span>
  );
}

export function TriggerBadge({ trigger }: { trigger: string }) {
  const meta = triggerLabels[trigger] ?? { label: trigger, tone: 'muted' as const };
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export function CoverageBadge({ status }: { status: string }) {
  const meta = coverageLabels[status] ?? { label: status, tone: 'muted' as const };
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export function VerificationBadge({ status }: { status: string }) {
  const meta = verificationLabels[status] ?? { label: status, tone: 'muted' as const };
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

// ---------------------------------------------------------------------------
// Metrics
// ---------------------------------------------------------------------------

export function Metric({
  label,
  value,
  hint,
  footnote,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  footnote?: ReactNode;
  tone?: 'default' | 'alert';
}) {
  return (
    <div className="min-w-0">
      <p
        className="truncate text-2xs font-medium uppercase tracking-[0.1em] text-ink-subtle"
        title={hint}
      >
        {label}
      </p>
      <p
        className={clsx(
          'tabular mt-1.5 text-2xl font-semibold tracking-tight',
          tone === 'alert' ? 'text-high' : 'text-ink',
        )}
      >
        {value}
      </p>
      {footnote ? <p className="mt-1 text-2xs text-ink-subtle">{footnote}</p> : null}
    </div>
  );
}

export function MetricGrid({ children, columns = 3 }: { children: ReactNode; columns?: number }) {
  return (
    <div
      className={clsx(
        'grid gap-x-6 gap-y-5',
        columns === 2 && 'grid-cols-2',
        columns === 3 && 'grid-cols-2 md:grid-cols-3',
        columns === 4 && 'grid-cols-2 lg:grid-cols-4',
        columns === 6 && 'grid-cols-2 md:grid-cols-3 xl:grid-cols-6',
      )}
    >
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// States
// ---------------------------------------------------------------------------

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-line bg-surface/50 px-6 py-12 text-center">
      {icon ? <div className="mb-3 text-ink-subtle">{icon}</div> : null}
      <p className="text-sm font-medium text-ink">{title}</p>
      {description ? (
        <div className="mt-1.5 max-w-md text-xs leading-relaxed text-ink-muted">
          {description}
        </div>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  title = 'Something did not work',
  detail,
  action,
}: {
  title?: string;
  detail?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-high/30 bg-high/5 px-5 py-4">
      <p className="text-sm font-semibold text-high">{title}</p>
      {detail ? (
        <div className="mt-1.5 text-xs leading-relaxed text-ink-muted">{detail}</div>
      ) : null}
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('skeleton rounded', className)} />;
}

export function Callout({
  tone = 'muted',
  title,
  children,
}: {
  tone?: Tone;
  title?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={clsx('rounded-lg border px-4 py-3 text-xs leading-relaxed', toneClasses[tone])}>
      {title ? <p className="mb-1 font-semibold">{title}</p> : null}
      <div className={clsx(tone === 'muted' && 'text-ink-muted')}>{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Data display
// ---------------------------------------------------------------------------

export function DefinitionRow({
  term,
  children,
}: {
  term: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex gap-4 border-b border-line py-2 last:border-0">
      <dt className="w-40 shrink-0 text-xs text-ink-subtle">{term}</dt>
      <dd className="min-w-0 flex-1 text-xs text-ink">{children}</dd>
    </div>
  );
}

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className="scroll-slim -mx-1 overflow-x-auto px-1">
      <table className={clsx('w-full border-collapse text-xs', className)}>{children}</table>
    </div>
  );
}

export function Th({
  children,
  align = 'left',
  className,
}: {
  children?: ReactNode;
  align?: 'left' | 'right' | 'center';
  className?: string;
}) {
  return (
    <th
      className={clsx(
        'border-b border-line pb-2 pr-4 text-2xs font-semibold uppercase tracking-[0.08em] text-ink-subtle last:pr-0',
        align === 'right' && 'text-right',
        align === 'center' && 'text-center',
        align === 'left' && 'text-left',
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  align = 'left',
  className,
}: {
  children?: ReactNode;
  align?: 'left' | 'right' | 'center';
  className?: string;
}) {
  return (
    <td
      className={clsx(
        'border-b border-line py-2.5 pr-4 align-top text-ink last:pr-0',
        align === 'right' && 'tabular text-right',
        align === 'center' && 'text-center',
        className,
      )}
    >
      {children}
    </td>
  );
}

/** A horizontal proportion bar. Used for score factors and distributions. */
export function Bar({
  value,
  max,
  tone = 'accent',
  className,
}: {
  value: number;
  max: number;
  tone?: 'accent' | 'positive' | 'negative' | 'muted';
  className?: string;
}) {
  const pct = max > 0 ? Math.min(100, Math.abs(value / max) * 100) : 0;
  const fill = {
    accent: 'bg-accent',
    positive: 'bg-low',
    negative: 'bg-high',
    muted: 'bg-line-strong',
  }[tone];
  return (
    <div className={clsx('h-1.5 w-full overflow-hidden rounded-full bg-raised', className)}>
      <div className={clsx('h-full rounded-full transition-all', fill)} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <code
      className={clsx(
        'rounded bg-raised px-1 py-0.5 font-mono text-2xs text-ink-muted',
        className,
      )}
    >
      {children}
    </code>
  );
}
