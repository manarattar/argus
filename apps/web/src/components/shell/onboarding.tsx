'use client';

import { usePathname } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * First-visit guided tour. One element is spotlighted at a time; the tour
 * never creates a case or calls the model. Steps whose target is not on the
 * page (the runtime panel on a phone, say) are skipped.
 */

type Step = { target: string; title: string; body: string; eyebrow?: string; fallback?: boolean };
type Tour = { key: string; steps: Step[] };

const OVERVIEW: Tour = {
  key: 'argus.onboarded.v1',
  steps: [
    {
      target: '', eyebrow: 'The idea', title: 'What is ARGUS?',
      body: 'Counterparty-risk analysts spend days reading scattered documents. ARGUS reads a case file, links extracted evidence to source passages, checks policy, challenges its conclusions, and calculates a rating by arithmetic before a human decides. All data is synthetic; this is a portfolio demonstration.',
    },
    {
      target: 'nav',
      title: 'Find your way around',
      body: 'Investigate has Cases, Evidence Graph for tracing ratings to sources, and Scenario Lab for testing changes. Assure has Evaluation Lab for quality checks, AI Operations for run health, and Audit Trail for actions. Explain has Value Case for illustrative savings and Architecture for how the system fits together.',
    },
    {
      target: 'overview',
      title: 'The book at a glance',
      body: 'These tiles count active cases, cases waiting for review, run time, analyst changes, evidence coverage, and estimated model cost. They describe the workload and system; none is a final credit decision.',
    },
    {
      target: 'cases',
      title: 'One row per counterparty',
      body: 'Each row is one organisation being reviewed. Its rating is provisional and evidence strength tells you how well the file supports it. Open a case such as Northstar to inspect the reasoning.',
    },
    {
      target: 'risk',
      title: 'Where the book is risky',
      body: 'Provisional ratings across every investigation, from Low to High. A rating is computed by the scoring engine from the findings, so it shows where analyst attention is likely to be needed, not a final decision.',
    },
    {
      target: 'health',
      title: 'Is the system healthy?',
      body: 'Step-level reliability across every run: how many steps executed, how many succeeded or failed, and how often the model output needed a retry. Use it to judge whether the AI itself behaved before trusting its answers.',
    },
    {
      target: 'attention',
      title: 'What needs a human',
      body: 'Cases held by a control or waiting on an analyst decision. They do not clear themselves: ARGUS recommends, and a named person approves, adjusts, escalates or rejects at the review gate.',
    },
    {
      target: 'runtime', fallback: true,
      title: 'Demo mode or live',
      body: 'Demo mode replays recorded model responses, so the tour works without an API key. Live mode makes real model calls. The indicator at the bottom of the menu tells you which produced the answers.',
    },
    { target: 'tour-button', title: 'Come back any time', body: 'Use How it works in the header to replay the tour for the page you are on.' },
  ],
};

const CASE: Tour = {
  key: 'argus.case-tour.v1',
  steps: [
    {
      target: 'start',
      title: 'Run the investigation',
      body: 'Start the eight steps in order: plan the review, extract evidence, identify risks, match policy, challenge findings, verify sources, calculate a score, and synthesise a report. The tour leaves the run under your control.',
    },
    {
      target: 'case-summary',
      title: 'The provisional rating',
      body: 'Computed by the scoring engine from the findings, policy matches and grounded evidence. It is not free text from the model.',
    },
    {
      target: 'tab-assessment', title: 'Assessment', body: 'See the provisional rating, the main factors driving it, and how confident the system is in the evidence. Review weak support before making a decision.',
    },
    {
      target: 'tab-findings',
      title: 'Findings and the challenger',
      body: 'Each risk has a severity and likelihood. A challenger pass argues against the finding so the analyst can spot weak or mistaken conclusions.',
    },
    {
      target: 'tab-evidence',
      title: 'Evidence with citations',
      body: 'Every claim cites a passage in a source document. A grounding check verifies that the quoted passage really exists.',
    },
    { target: 'tab-policy', title: 'Policy', body: 'See which findings match a policy clause and why. A match shows the rule behind a concern; it does not make the decision for you.' },
    { target: 'tab-trace', title: 'Trace', body: 'Follow the run step by step, including time spent and any errors. This shows what the agents actually did and where a result may be incomplete.' },
    { target: 'tab-ask', title: 'Ask ARGUS', body: 'Ask questions about this case. Answers are limited to case evidence and include citations you can open and check.' },
    { target: 'tab-report', title: 'Report', body: 'Read the generated analyst memo. Check its claims and citations before using it in a review.' },
    { target: 'tab-audit', title: 'Audit', body: 'This immutable event log records actions in order, including the actor and what changed. It lets a reviewer reconstruct the history.' },
    {
      target: 'review-gate',
      title: 'The human review gate',
      body: 'The AI investigates and recommends. A named analyst approves, rejects or escalates, and nothing is final until then.',
    },
  ],
};

const CASES_OVERVIEW: Tour = { ...OVERVIEW, key: 'argus.tour.cases.v1' };

const PAGE_TOURS: Record<string, Tour> = Object.fromEntries(
  ([
    ['graph', 'Evidence Graph', 'Follow a rating through findings and evidence to the exact source passage. This shows where each conclusion came from.'],
    ['scenario', 'Scenario Lab', 'Change an input, such as a missing document or covenant breach, and see the projected effect on the rating. The underlying case is not changed.'],
    ['evaluation', 'Evaluation Lab', 'The 53-case suite measures accuracy, whether claims cite real passages, and whether the challenger catches weak findings. It shows how the system is measured before it is trusted.'],
    ['operations', 'AI Operations', 'Check how many runs complete, how long they take, their token cost, and their error rate. These numbers help find slow or failing steps.'],
    ['audit', 'Audit Trail', 'See each recorded action in order, with who or what performed it. Use this history to trace how a case reached its current state.'],
    ['value', 'Value Case', 'This is an illustrative model of analyst hours saved, not a forecast. Change its assumptions to see how the estimate moves.'],
    ['architecture', 'Architecture', 'See how the API, eight-step workflow, pgvector passage retrieval, and human review gate fit together. The diagram explains where evidence and decisions move.'],
  ] as const).map(([path, title, body]) => [`/${path}`, {
    key: `argus.tour.${path}.v1`,
    steps: [
      { target: '', title, body },
      { target: 'page-header', title: 'Where to look', body: 'The heading and summary here say what the page shows. Everything below is built from the synthetic sample cases. Replay this guide any time with How it works.' },
    ],
  }]),
);

const EVENT = 'argus:tour';

function tourFor(pathname: string): { tour: Tour; auto: boolean } {
  if (PAGE_TOURS[pathname]) return { tour: PAGE_TOURS[pathname], auto: true };
  if (/^\/cases\/[^/]+/.test(pathname)) return { tour: CASE, auto: true };
  if (pathname === '/') return { tour: OVERVIEW, auto: true };
  if (pathname === '/cases') return { tour: CASES_OVERVIEW, auto: true };
  return { tour: OVERVIEW, auto: false };
}

function find(target: string): HTMLElement | null {
  if (!target) return null;
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
      data-tour="tour-button"
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
    if (document.querySelector('.tour-layer')) return;
    const steps = tour.steps
      .filter((step) => !step.target || find(step.target) || step.fallback)
      .map((step) => (step.target && !find(step.target) ? { ...step, target: '' } : step));
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
    const gate = tour === CASE ? 'case-summary' : pathname === '/cases' ? 'cases' : tour === OVERVIEW ? 'nav' : 'page-header';
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
    const target = run.steps[index]?.target ?? '';
    if (!target) {
      setBox(null);
      const phone = window.innerWidth <= 520;
      setNarrow(phone);
      setCardPos(phone ? null : { top: Math.max(12, (window.innerHeight - (cardRef.current?.offsetHeight ?? 220)) / 2), left: Math.max(12, (window.innerWidth - (cardRef.current?.offsetWidth ?? 340)) / 2) });
      return;
    }
    const el = find(target);
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
      {!step.target ? <div className="tour-backdrop" /> : null}
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
        {step.eyebrow ? <div className="tour-count">{step.eyebrow}</div> : null}
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
