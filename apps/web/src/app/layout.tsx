import type { Metadata, Viewport } from 'next';

import { MobileNav, Sidebar, ThemeToggle } from '@/components/shell/navigation';
import { getRuntime } from '@/lib/api';

import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'ARGUS — Agentic Risk Governance & Understanding System',
    template: '%s · ARGUS',
  },
  description:
    'From fragmented evidence to explainable risk intelligence. AI investigates and recommends; humans decide.',
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f8fafc' },
    { media: '(prefers-color-scheme: dark)', color: '#0a0e14' },
  ],
};

/**
 * Applies the stored theme before first paint, so a dark-theme user never sees
 * a white flash on navigation.
 */
const THEME_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem('argus-theme');
    var dark = stored === 'dark' || (!stored && window.matchMedia('(prefers-color-scheme: dark)').matches);
    if (dark) document.documentElement.classList.add('dark');
  } catch (e) {}
})();
`;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const runtime = await getRuntime();

  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2 focus:text-xs focus:shadow-pop"
        >
          Skip to content
        </a>

        <div className="flex h-screen overflow-hidden">
          <Sidebar runtime={runtime} />

          <div className="flex min-w-0 flex-1 flex-col">
            <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-line bg-surface px-4 sm:gap-4 sm:px-6">
              <div className="flex min-w-0 items-center gap-2 sm:gap-3">
                <MobileNav runtime={runtime} />
                <p className="truncate text-xs text-ink-muted">
                  Independent portfolio demonstration. All data is synthetic. Not affiliated with,
                  or endorsed by, any financial institution.
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                {runtime ? (
                  <span className="hidden text-2xs text-ink-subtle md:inline">
                    {runtime.database} · {runtime.environment}
                  </span>
                ) : null}
                <ThemeToggle />
              </div>
            </header>

            <main id="main" className="scroll-slim flex-1 overflow-y-auto bg-canvas">
              <div className="mx-auto max-w-[1400px] px-4 py-5 sm:px-6 sm:py-7">{children}</div>
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
