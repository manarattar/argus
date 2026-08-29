'use client';

import clsx from 'clsx';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';

import type { RuntimeStatus } from '@/lib/types';

/**
 * Navigation is grouped by the job being done, not by data type. An analyst
 * working a case, a reviewer checking the system, and an interviewer reading
 * the architecture are three different sessions, and the grouping makes that
 * legible at a glance.
 */
const GROUPS: { label: string; items: { href: string; label: string; hint: string }[] }[] = [
  {
    label: 'Investigate',
    items: [
      { href: '/', label: 'Overview', hint: 'Portfolio status and what needs attention' },
      { href: '/cases', label: 'Cases', hint: 'Counterparty reviews' },
      { href: '/graph', label: 'Evidence Graph', hint: 'Lineage from rating to source' },
      { href: '/scenario', label: 'Scenario Lab', hint: 'Projected effect of a changed input' },
    ],
  },
  {
    label: 'Assure',
    items: [
      { href: '/evaluation', label: 'Evaluation Lab', hint: 'How well the system performs' },
      { href: '/operations', label: 'AI Operations', hint: 'Throughput, cost and reliability' },
      { href: '/audit', label: 'Audit Trail', hint: 'Everything that happened, in order' },
    ],
  },
  {
    label: 'Explain',
    items: [
      { href: '/value', label: 'Value Case', hint: 'Illustrative business-case model' },
      { href: '/architecture', label: 'Architecture', hint: 'How the system is built' },
      { href: '/settings', label: 'Settings', hint: 'Runtime configuration' },
    ],
  },
];

function isActive(pathname: string, href: string): boolean {
  if (href === '/') return pathname === '/';
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar({ runtime }: { runtime: RuntimeStatus | null }) {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className="flex h-full w-56 shrink-0 flex-col border-r border-line bg-surface"
    >
      <Link
        href="/"
        className="flex items-center gap-2.5 border-b border-line px-4 py-4 hover:bg-raised"
      >
        <Mark />
        <span className="min-w-0">
          <span className="block text-sm font-semibold tracking-[0.08em] text-ink">ARGUS</span>
          <span className="block truncate text-2xs text-ink-subtle">Risk Intelligence</span>
        </span>
      </Link>

      <div className="scroll-slim flex-1 overflow-y-auto px-2.5 py-4">
        {GROUPS.map((group) => (
          <div key={group.label} className="mb-5 last:mb-0">
            <p className="px-2 pb-1.5 text-2xs font-semibold uppercase tracking-[0.12em] text-ink-subtle">
              {group.label}
            </p>
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const active = isActive(pathname, item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      title={item.hint}
                      aria-current={active ? 'page' : undefined}
                      className={clsx(
                        'flex items-center gap-2 rounded px-2 py-1.5 text-xs transition-colors',
                        active
                          ? 'bg-accent-soft font-medium text-accent'
                          : 'text-ink-muted hover:bg-raised hover:text-ink',
                      )}
                    >
                      <span
                        className={clsx(
                          'h-3.5 w-0.5 rounded-full',
                          active ? 'bg-accent' : 'bg-transparent',
                        )}
                      />
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      <RuntimeFooter runtime={runtime} />
    </nav>
  );
}

function Mark() {
  return (
    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded border border-accent/25 bg-accent-soft">
      <svg viewBox="0 0 20 20" className="h-4 w-4 text-accent" aria-hidden>
        <circle cx="10" cy="10" r="7.25" stroke="currentColor" strokeWidth="1.4" fill="none" />
        <circle cx="10" cy="10" r="2.6" fill="currentColor" />
        <path
          d="M10 1.4v2.6M10 16v2.6M1.4 10h2.6M16 10h2.6"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

/**
 * The mode indicator is permanent and always visible.
 *
 * A reviewer should never have to work out whether the numbers on screen came
 * from a live model or from a recording, so the answer sits in the chrome
 * rather than behind a menu.
 */
function RuntimeFooter({ runtime }: { runtime: RuntimeStatus | null }) {
  if (!runtime) {
    return (
      <div className="border-t border-line px-4 py-3">
        <p className="flex items-center gap-1.5 text-2xs font-medium text-high">
          <span className="h-1.5 w-1.5 rounded-full bg-high" />
          API unreachable
        </p>
        <p className="mt-1 text-2xs leading-relaxed text-ink-subtle">
          Start the backend with <code className="font-mono">make api</code>.
        </p>
      </div>
    );
  }

  const demo = runtime.mode === 'demo';
  return (
    <div className="border-t border-line px-4 py-3" title={runtime.explanation}>
      <p
        className={clsx(
          'flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-[0.1em]',
          demo ? 'text-moderate' : 'text-low',
        )}
      >
        <span className={clsx('h-1.5 w-1.5 rounded-full', demo ? 'bg-moderate' : 'bg-low')} />
        {demo ? 'Demo mode' : 'Live inference'}
      </p>
      <p className="mt-1 truncate text-2xs text-ink-subtle" title={runtime.model}>
        {demo ? 'Recorded responses' : runtime.model}
      </p>
      <p className="mt-0.5 truncate text-2xs text-ink-subtle" title={runtime.embedding.description}>
        {runtime.embedding.semantic ? 'Semantic' : 'Lexical'} retrieval
      </p>
    </div>
  );
}

/** Theme toggle. Preference persists locally; system preference is the default. */
export function ThemeToggle() {
  const [dark, setDark] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const stored = window.localStorage.getItem('argus-theme');
    const prefersDark =
      stored === 'dark' ||
      (!stored && window.matchMedia('(prefers-color-scheme: dark)').matches);
    setDark(prefersDark);
    document.documentElement.classList.toggle('dark', prefersDark);
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle('dark', next);
    window.localStorage.setItem('argus-theme', next ? 'dark' : 'light');
  }

  if (!mounted) {
    return <span className="h-7 w-7" aria-hidden />;
  }

  return (
    <button
      type="button"
      onClick={toggle}
      title={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      className="flex h-7 w-7 items-center justify-center rounded text-ink-muted transition-colors hover:bg-raised hover:text-ink"
    >
      {dark ? (
        <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor" aria-hidden>
          <path d="M10 3.5a1 1 0 0 1 1 1v.75a1 1 0 1 1-2 0V4.5a1 1 0 0 1 1-1Zm0 9a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Zm6.5-2.5a1 1 0 0 1-1 1h-.75a1 1 0 1 1 0-2h.75a1 1 0 0 1 1 1Zm-11.75 1a1 1 0 1 0 0-2H4a1 1 0 1 0 0 2h.75ZM10 14.75a1 1 0 0 1 1 1v.75a1 1 0 1 1-2 0v-.75a1 1 0 0 1 1-1Zm4.6-9.35a1 1 0 0 1 0 1.42l-.53.53a1 1 0 0 1-1.42-1.42l.53-.53a1 1 0 0 1 1.42 0ZM6.35 13.65a1 1 0 0 1 0 1.41l-.53.53a1 1 0 0 1-1.42-1.41l.53-.53a1 1 0 0 1 1.42 0Zm8.25 1.94-.53-.53a1 1 0 0 1 1.42-1.41l.53.53a1 1 0 0 1-1.42 1.41ZM5.82 5.4l.53.53A1 1 0 1 1 4.93 7.35l-.53-.53A1 1 0 0 1 5.82 5.4Z" />
        </svg>
      ) : (
        <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor" aria-hidden>
          <path d="M16.3 12.4a6.5 6.5 0 0 1-8.7-8.7 1 1 0 0 0-1.3-1.3 8.5 8.5 0 1 0 11.3 11.3 1 1 0 0 0-1.3-1.3Z" />
        </svg>
      )}
    </button>
  );
}
