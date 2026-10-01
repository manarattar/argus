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

/** The ARGUS wordmark, linking home. Shared by the sidebar and the mobile drawer. */
function Wordmark({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <Link
      href="/"
      onClick={onNavigate}
      className="flex items-center gap-2.5 border-b border-line px-4 py-4 hover:bg-raised"
    >
      <Mark />
      <span className="min-w-0">
        <span className="block font-display text-sm font-semibold tracking-[0.08em] text-ink">ARGUS</span>
        <span className="block truncate text-2xs text-ink-subtle">Risk Intelligence</span>
      </span>
    </Link>
  );
}

/**
 * The grouped link list. Identical in the desktop sidebar and the mobile
 * drawer. The first group is always open; the others are menus that open on
 * demand (or by themselves when the current page lives inside them), which
 * keeps the rail short.
 */
function NavGroups({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const [opened, setOpened] = useState<Record<string, boolean>>({});

  return (
    <div className="scroll-slim flex-1 overflow-y-auto px-2.5 py-4">
      {GROUPS.map((group, index) => {
        const holdsActive = group.items.some((item) => isActive(pathname, item.href));
        const open = index === 0 || holdsActive || Boolean(opened[group.label]);
        return (
          <div key={group.label} className="mb-3 last:mb-0">
            {index === 0 ? (
              <p className="px-2 pb-1.5 text-2xs font-semibold uppercase tracking-[0.12em] text-ink-subtle">
                {group.label}
              </p>
            ) : (
              <button
                type="button"
                aria-expanded={open}
                onClick={() => setOpened((current) => ({ ...current, [group.label]: !open }))}
                className="flex min-h-[32px] w-full items-center justify-between rounded px-2 text-2xs font-semibold uppercase tracking-[0.12em] text-ink-subtle hover:bg-raised hover:text-ink"
              >
                {group.label}
                <svg
                  viewBox="0 0 20 20"
                  className={clsx('h-3 w-3 transition-transform', open && 'rotate-90')}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  aria-hidden
                >
                  <path d="M7 4l6 6-6 6" />
                </svg>
              </button>
            )}
            {open ? (
              <ul className="space-y-0.5">
                {group.items.map((item) => {
                  const active = isActive(pathname, item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        title={item.hint}
                        onClick={onNavigate}
                        aria-current={active ? 'page' : undefined}
                        className={clsx(
                          'flex min-h-[32px] items-center gap-2 rounded px-2 py-1.5 text-xs transition-colors',
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
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Primary navigation, persistent from `lg` up. Below that the viewport is too
 * narrow to spend 224px on chrome, so it is hidden and {@link MobileNav} takes
 * over with a slide-in drawer.
 */
export function Sidebar({ runtime }: { runtime: RuntimeStatus | null }) {
  return (
    <nav
      aria-label="Primary"
      data-tour="nav"
      className="hidden h-full w-56 shrink-0 flex-col border-r border-line bg-surface lg:flex"
    >
      <Wordmark />
      <NavGroups />
      <RuntimeFooter runtime={runtime} />
    </nav>
  );
}

/**
 * Mobile navigation: a menu button that opens the same nav as a drawer over a
 * dimmed backdrop. Rendered in the header, hidden from `lg` up where the
 * persistent {@link Sidebar} is shown instead.
 */
export function MobileNav({ runtime }: { runtime: RuntimeStatus | null }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  // Close on navigation.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // While open: close on Escape, and stop the page behind from scrolling.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open navigation"
        aria-expanded={open}
        data-tour="nav"
        className="-ml-1 flex h-9 w-9 shrink-0 items-center justify-center rounded text-ink-muted hover:bg-raised hover:text-ink lg:hidden"
      >
        <svg
          viewBox="0 0 20 20"
          className="h-4 w-4"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          aria-hidden
        >
          <path d="M3 6h14M3 10h14M3 14h14" />
        </svg>
      </button>

      {open ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            tabIndex={-1}
            onClick={() => setOpen(false)}
            className="absolute inset-0 h-full w-full cursor-default bg-ink/40"
          />
          <nav
            aria-label="Primary"
            className="animate-fade-up absolute left-0 top-0 flex h-full w-64 max-w-[82vw] flex-col border-r border-line bg-surface shadow-pop"
          >
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close navigation"
              className="absolute right-2 top-3.5 flex h-8 w-8 items-center justify-center rounded text-ink-muted hover:bg-raised hover:text-ink"
            >
              <svg
                viewBox="0 0 20 20"
                className="h-4 w-4"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                aria-hidden
              >
                <path d="M5 5l10 10M15 5L5 15" />
              </svg>
            </button>
            <Wordmark onNavigate={() => setOpen(false)} />
            <NavGroups onNavigate={() => setOpen(false)} />
            <RuntimeFooter runtime={runtime} />
          </nav>
        </div>
      ) : null}
    </>
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
    <div className="border-t border-line px-4 py-3" title={runtime.explanation} data-tour="runtime">
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

/** Theme toggle. Light is the default; dark is opt-in and remembered. */
export function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.getAttribute('data-theme') === 'dark');
  }, []);

  function toggle() {
    const next = dark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try {
      window.localStorage.setItem('theme', next);
    } catch {
      /* storage can be unavailable; the choice then lasts for this visit */
    }
    setDark(next === 'dark');
  }

  const label = dark ? 'Switch to light mode' : 'Switch to dark mode';
  return (
    <button
      type="button"
      onClick={toggle}
      title={label}
      aria-label={label}
      className="flex h-9 w-9 items-center justify-center rounded text-ink-muted transition-colors hover:bg-raised hover:text-ink"
    >
      {dark ? (
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  );
}
