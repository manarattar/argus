/**
 * Presentation helpers.
 *
 * Formatting rules that carry meaning live here rather than in components, so
 * a risk level looks identical everywhere it appears and a cost is always
 * marked as an estimate.
 */

import type { EvidenceStrength, RiskLevel } from './types';

export const RISK_LEVELS: RiskLevel[] = ['low', 'moderate', 'elevated', 'high'];

/** Tailwind classes per risk level. The only saturated colour in the product. */
export const riskClasses: Record<RiskLevel, { text: string; bg: string; border: string; dot: string }> =
  {
    low: {
      text: 'text-low',
      bg: 'bg-low/10',
      border: 'border-low/30',
      dot: 'bg-low',
    },
    moderate: {
      text: 'text-moderate',
      bg: 'bg-moderate/10',
      border: 'border-moderate/30',
      dot: 'bg-moderate',
    },
    elevated: {
      text: 'text-elevated',
      bg: 'bg-elevated/10',
      border: 'border-elevated/30',
      dot: 'bg-elevated',
    },
    high: {
      text: 'text-high',
      bg: 'bg-high/10',
      border: 'border-high/30',
      dot: 'bg-high',
    },
  };

export function riskLevelOf(value: string | null | undefined): RiskLevel | null {
  return value && RISK_LEVELS.includes(value as RiskLevel) ? (value as RiskLevel) : null;
}

/**
 * Evidence strength deliberately does not use the risk palette. It answers a
 * different question - how well do we know this? - and colouring it the same
 * way would invite the reader to conflate the two.
 */
export const strengthClasses: Record<EvidenceStrength, string> = {
  strong: 'text-ink border-line-strong bg-raised',
  moderate: 'text-ink-muted border-line bg-raised',
  weak: 'text-elevated border-elevated/30 bg-elevated/10',
  insufficient: 'text-high border-high/30 bg-high/10',
};

export function titleCase(value: string): string {
  return value
    .replace(/[_-]/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function formatDuration(ms: number): string {
  if (!ms) return '—';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

export function formatCurrency(value: number, digits = 2): string {
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatCompactCurrency(value: number): string {
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'USD',
    notation: Math.abs(value) >= 10_000 ? 'compact' : 'standard',
    maximumFractionDigits: Math.abs(value) >= 10_000 ? 1 : 0,
  }).format(value);
}

export function formatNumber(value: number, digits = 0): string {
  return new Intl.NumberFormat('en-GB', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(new Date(iso));
}

export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(iso);
}

/** Trigger types, ordered by how much attention they warrant. */
export const triggerLabels: Record<string, { label: string; tone: 'alert' | 'warn' | 'muted' }> = {
  potential_breach: { label: 'Potential breach', tone: 'alert' },
  threshold_met: { label: 'Threshold met', tone: 'warn' },
  review_trigger: { label: 'Review trigger', tone: 'warn' },
  informational: { label: 'Informational', tone: 'muted' },
};

export const coverageLabels: Record<string, { label: string; tone: 'ok' | 'warn' | 'alert' }> = {
  complete: { label: 'Complete', tone: 'ok' },
  partial: { label: 'Partial', tone: 'warn' },
  missing: { label: 'Missing', tone: 'alert' },
};

export const verificationLabels: Record<string, { label: string; tone: 'ok' | 'warn' | 'alert' }> =
  {
    supported: { label: 'Supported', tone: 'ok' },
    partially_supported: { label: 'Partially supported', tone: 'warn' },
    unsupported: { label: 'Unsupported', tone: 'alert' },
    conflicting: { label: 'Conflicting evidence', tone: 'alert' },
  };

export const stepStatusLabels: Record<string, { label: string; tone: 'ok' | 'warn' | 'alert' | 'muted' }> =
  {
    succeeded: { label: 'Succeeded', tone: 'ok' },
    running: { label: 'Running', tone: 'muted' },
    pending: { label: 'Pending', tone: 'muted' },
    skipped: { label: 'Skipped', tone: 'muted' },
    retried: { label: 'Retried', tone: 'warn' },
    failed: { label: 'Failed', tone: 'alert' },
  };

/** Truncate on a word boundary so labels never end mid-word. */
export function truncate(text: string, limit: number): string {
  if (text.length <= limit) return text;
  const clipped = text.slice(0, limit);
  const lastSpace = clipped.lastIndexOf(' ');
  return `${clipped.slice(0, lastSpace > limit * 0.6 ? lastSpace : limit)}…`;
}
