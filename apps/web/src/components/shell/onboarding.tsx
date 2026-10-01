'use client';

import { usePathname } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * First-visit guided tour. One element is spotlighted at a time; the tour
 * never creates a case or calls the model. Steps whose target is not on the
 * page (the runtime panel on a phone, say) are skipped.
 */

type Step = { target: string; title: string; body: string };
type Tour = { key: string; steps: Step[] };

const OVERVIEW: Tour = {
  key: 'argus.onboarded.v1',
  steps: [
    {
      target: 'nav',
      title: 'Where things live',
      body: 'Investigate holds the cases and their evidence. Assure and Explain open as menus when you need the evaluation, audit trail or architecture.',
    },
    {
      target: 'overview',
      title: 'The book at a glance',
      body: 'Active cases, how many wait for a human decision, and how the ratings are spread. Nothing here is a final credit decision.',
    },
    {
      target: 'cases',
      title: 'One row per counterparty',
      body: 'Each row is a review of one organisation, with its provisional rating and how strong the evidence behind it is. Open one to see the file.',
    },
    {
      target: 'runtime',
      title: 'Demo mode or live',
      body: 'This always tells you whether the answers on screen come from recorded model responses or a live model. All data is synthetic.',
    },
  ],
};

const CASE: Tour = {
  key: 'argus.case-tour.v1',
  steps: [
    {
      target: 'start',
      title: 'Run the investigation',
      body: 'This starts the eight-step graph and takes a few seconds. The tour does not start it for you.',
    },
    {
      target: 'case-summary',
      title: 'The provisional rating',
      body: 'Computed by the scoring engine from the findings, policy matches and grounded evidence. It is not free text from the model.',
    },
    {
      target: 'tab-findings',
      title: 'Findings and the challenger',
      body: 'Every risk the system found, and the second pass that argues against it. Unresolved challenges are counted at the top.',
    },
    {
      target: 'tab-evidence',
      title: 'Evidence with citations',
      body: 'Each finding points back to the source passage it rests on, so a reviewer can check it rather than trust it.',
    },
    {
      target: 'review-gate',
      title: 'The human review gate',
      body: 'The AI investigates and recommends. A named analyst approves, rejects or escalates, and nothing is final until then.',
    },
  ],
};

const EVENT = 'argus:tour';

function tourFor(pathname: string): { tour: Tour; auto: boolean } {
  if (/^\/cases\/[^/]+/.test(pathname)) return { tour: CASE, auto: true };
  if (pathname === '/' || pathname === '/cases') return { tour: OVERVIEW, auto: true };
  return { tour: OVERVIEW, auto: false };
}

function find(target: string): HTMLElement | null {
  const nodes = Array.from(document.querySelectorAll<HTMLElement>(`[data-tour="${target}"]`));
  return (
    nodes.find((node) => {
      const rect = node.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    }) ?? null
  );
}

function seen(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === 'yes';
  } catch {
    return false;
  }
}

function mark(key: string) {
  try {
    window.localStorage.setItem(key, 'yes');
  } catch {
    /* ignore */
  }
}

export function TourButton() {
  return (
    <button
      type="button"
      onClick={() => window.dispatchEvent(new Event(EVENT))}
      className="flex h-9 items-center rounded px-2.5 text-xs font-medium text-ink-muted transition-colors hover:bg-raised hover:text-ink"
    >
      How it works
    </button>
  );
}

export function Onboarding() {
  const pathname = usePathname();
  const [run, setRun] = useState<{ tour: Tour; steps: Step[] } | null>(null);
  const [index, setIndex] = useState(0);
  const [box, setBox] = useState<{ top: number; left: number; width: number; height: number } | null>(null);
  const [narrow, setNarrow] = useState(false);
  const [cardPos, setCardPos] = useState<{ top: number; left: number } | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef<Element | null>(null);

  const begin = useCallback((tour: Tour) => {
    const steps = tour.steps.filter((step) => find(step.target));
    if (steps.length === 0) return;
    returnFocus.current = document.activeElement;
    setIndex(0);
    setRun({ tour, steps });
  }, []);

  const close = useCallback(() => {
    setRun((current) => {
      if (current) mark(current.tour.key);
      return null;
    });
    const el = returnFocus.current as HTMLElement | null;
    if (el && typeof el.focus === 'function') el.focus();
  }, []);

  // Auto-start on first visit once the page's own targets have rendered.
  useEffect(() => {
    const { tour, auto } = tourFor(pathname);
    if (!auto || seen(tour.key)) return;
    const gate = tour === CASE ? 'case-summary' : tour === OVERVIEW && pathname === '/cases' ? 'cases' : 'nav';
    let tries = 0;
    const timer = window.setInterval(() => {
      tries += 1;
      if (find(gate)) {
        window.clearInterval(timer);
        begin(tour);
      } else if (tries > 16) {
        window.clearInterval(timer);
      }
    }, 250);
    return () => window.clearInterval(timer);
  }, [pathname, begin]);

  // "How it works" replays the tour for the current page.
  useEffect(() => {
    const handler = () => begin(tourFor(pathname).tour);
    window.addEventListener(EVENT, handler);
    return () => window.removeEventListener(EVENT, handler);
  }, [pathname, begin]);

  // Close if the visitor navigates away mid-tour.
  useEffect(() => {
    setRun(null);
  }, [pathname]);

  const place = useCallback(() => {
    if (!run) return;
    const el = find(run.steps[index]?.target ?? "");
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const pad = 6;
    setBox({
      top: rect.top - pad,
      left: rect.left - pad,
      width: rect.width + pad * 2,
      height: rect.height + pad * 2,
    });
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const phone = vw <= 520;
    setNarrow(phone);
    if (phone) {
      setCardPos(null);
      return;
    }
    const card = cardRef.current;
    const cw = card?.offsetWidth ?? 340;
    const ch = card?.offsetHeight ?? 180;
    let top = rect.bottom + 14;
    if (top + ch > vh - 12) top = Math.max(12, rect.top - ch - 14);
    if (rect.top < 0 || rect.bottom > vh) top = Math.max(12, vh / 2 - ch / 2);
    const left = Math.min(Math.max(12, rect.left + rect.width / 2 - cw / 2), vw - cw - 12);
    setCardPos({ top, left });
  }, [run, index]);

  useEffect(() => {
    if (!run) return;
    const el = find(run.steps[index]?.target ?? "");
    el?.scrollIntoView({ block: 'center' });
    place();
    const t = window.setTimeout(place, 150);
    nextRef.current?.focus();
    return () => window.clearTimeout(t);
  }, [run, index, place]);

  useEffect(() => {
    if (!run) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
      } else if (event.key === 'ArrowRight') {
        setIndex((i) => (i + 1 < run.steps.length ? i + 1 : i));
      } else if (event.key === 'ArrowLeft') {
        setIndex((i) => Math.max(0, i - 1));
      }
    };
    window.addEventListener('keydown', onKey, true);
    window.addEventListener('resize', place);
    document.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('keydown', onKey, true);
      window.removeEventListener('resize', place);
      document.removeEventListener('scroll', place, true);
    };
  }, [run, close, place]);

  if (!run) return null;
  const step = run.steps[index];
  if (!step) return null;
  const last = index === run.steps.length - 1;

  return (
    <div className="tour-layer" role="dialog" aria-modal="true" aria-label="Guided tour">
      {box ? (
        <div
          className="tour-spot"
          style={{ top: box.top, left: box.left, width: box.width, height: box.height }}
        />
      ) : null}
      <div
        ref={cardRef}
        className={`tour-card${narrow ? ' sheet' : ''}`}
        style={!narrow && cardPos ? { top: cardPos.top, left: cardPos.left } : undefined}
      >
        <div className="tour-count">
          {index + 1} / {run.steps.length}
        </div>
        <h2 className="tour-title">{step.title}</h2>
        <p className="tour-body">{step.body}</p>
        <div className="tour-actions">
          {!last ? (
            <button type="button" className="tour-skip" onClick={close}>
              Skip the tour
            </button>
          ) : null}
          <span className="tour-gap" />
          {index > 0 ? (
            <button type="button" onClick={() => setIndex(index - 1)}>
              Back
            </button>
          ) : null}
          <button
            ref={nextRef}
            type="button"
            className="tour-next"
            onClick={() => (last ? close() : setIndex(index + 1))}
          >
            {last ? 'Got it' : 'Next'}
          </button>
        </div>
      </div>
    </div>
  );
}
