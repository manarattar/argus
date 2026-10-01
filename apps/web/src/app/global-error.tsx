'use client';

/**
 * Last-resort boundary for errors in the root layout itself. It replaces the
 * whole document, so it cannot rely on the app's stylesheet or components.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 16,
          background: '#f4f5f2',
          color: '#18211e',
          fontFamily: 'system-ui, -apple-system, Segoe UI, sans-serif',
        }}
      >
        <div
          role="alert"
          style={{
            maxWidth: 440,
            background: '#fffffd',
            border: '1px solid #dce0da',
            borderLeft: '3px solid #ac202a',
            padding: 24,
          }}
        >
          <p style={{ margin: 0, fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#ac202a', fontWeight: 600 }}>
            ARGUS
          </p>
          <h1 style={{ margin: '6px 0 8px', fontSize: 20 }}>Something went wrong</h1>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.5, color: '#44504c' }}>
            The application hit an error and stopped. Nothing was changed. Reload to carry on.
          </p>
          <p style={{ margin: '12px 0 0', fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace', color: '#44504c', wordBreak: 'break-word' }}>
            {(error.message || 'Unexpected error').slice(0, 240)}
          </p>
          <button
            type="button"
            onClick={reset}
            style={{
              marginTop: 16,
              minHeight: 40,
              padding: '0 16px',
              border: 0,
              borderRadius: 4,
              background: '#1f4d45',
              color: '#fffffd',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
