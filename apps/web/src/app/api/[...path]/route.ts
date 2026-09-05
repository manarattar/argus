/**
 * Same-origin proxy to the API.
 *
 * Why this exists rather than a `rewrites()` entry in next.config: Next
 * evaluates `rewrites()` during the build and writes the resolved destination
 * into the routes manifest. The backend address would therefore be baked into
 * the image, and moving the API would mean rebuilding the frontend. A Route
 * Handler reads the environment on each request, so the destination is genuinely
 * configuration.
 *
 * Two further benefits fall out of proxying rather than calling the API
 * directly from the browser:
 *
 *  - the browser only ever talks to its own origin, so the deployment needs no
 *    CORS grant and no preflight round-trip;
 *  - the API's address is never exposed to the client at all.
 */

import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

/**
 * Some hosts expose a service address without a scheme (Render's `fromService`
 * is one), and `fetch` rejects that. Assume HTTPS unless it looks local.
 */
function apiBase(): string {
  const value = (process.env.API_BASE_URL ?? '').trim().replace(/\/$/, '');
  if (!value) return 'http://127.0.0.1:8000';
  if (/^https?:\/\//.test(value)) return value;
  const isLocal = /^(localhost|127\.0\.0\.1|\[::1\]|[a-z0-9-]+):\d+$/i.test(value);
  return `${isLocal ? 'http' : 'https'}://${value}`;
}

/** Headers worth passing upstream. The rest are hop-by-hop or set by fetch. */
const FORWARD_REQUEST_HEADERS = ['content-type', 'accept', 'x-request-id'];

/** Headers worth returning. Notably includes the ones our API sets itself. */
const FORWARD_RESPONSE_HEADERS = [
  'content-type',
  'content-disposition',
  'x-request-id',
  'x-response-time-ms',
  'retry-after',
];

async function proxy(request: NextRequest, path: string[]): Promise<Response> {
  const target = `${apiBase()}/api/${path.join('/')}${request.nextUrl.search}`;

  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  // Preserve the caller's address so the API's rate limiter keys on the real
  // client rather than on this server, which would otherwise put every visitor
  // into one bucket.
  const forwardedFor = request.headers.get('x-forwarded-for');
  if (forwardedFor) headers.set('x-forwarded-for', forwardedFor);

  const method = request.method;
  const body =
    method === 'GET' || method === 'HEAD' ? undefined : await request.text();

  let upstream: Response;
  try {
    upstream = await fetch(target, { method, headers, body, cache: 'no-store' });
  } catch (error) {
    // The API being unreachable is a normal state during a cold start on a
    // free tier, so it gets a clear message rather than an opaque 500.
    return NextResponse.json(
      {
        detail:
          'The ARGUS API is not reachable. If this deployment has just woken ' +
          'from idle, give it a few seconds and retry.',
        cause: error instanceof Error ? error.message : 'unknown',
      },
      { status: 502 },
    );
  }

  const responseHeaders = new Headers();
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }

  // Streamed through rather than buffered, so the PDF export does not have to
  // be held in memory here.
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

type Context = { params: { path: string[] } };

export async function GET(request: NextRequest, { params }: Context) {
  return proxy(request, params.path);
}

export async function POST(request: NextRequest, { params }: Context) {
  return proxy(request, params.path);
}

export async function PATCH(request: NextRequest, { params }: Context) {
  return proxy(request, params.path);
}

export async function DELETE(request: NextRequest, { params }: Context) {
  return proxy(request, params.path);
}
