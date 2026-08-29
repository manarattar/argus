/**
 * Typed API client.
 *
 * Server components fetch through `serverGet`, which runs uncached so the
 * dashboard always reflects the current database rather than a build-time
 * snapshot. Client components use `clientFetch`, which surfaces the API's own
 * error message: when a step fails - a missing recording in Demo Mode, a
 * refused approval - the analyst should read the real reason, not "something
 * went wrong".
 */

import type {
  ArchitectureData,
  AuditEvent,
  CaseDetail,
  CaseSummary,
  DashboardData,
  EvalRun,
  EvidenceGraphData,
  GroundedAnswer,
  InvestigationDetail,
  OperationsData,
  RuntimeStatus,
  ScenarioResult,
  ScenarioVariable,
  ValueCaseResult,
} from './types';

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '') ?? 'http://127.0.0.1:8000';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly requestId?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function readError(response: Response): Promise<never> {
  let detail = `Request failed with status ${response.status}`;
  let requestId: string | undefined;
  try {
    const body = (await response.json()) as { detail?: unknown; request_id?: string };
    if (typeof body.detail === 'string') {
      detail = body.detail;
    } else if (Array.isArray(body.detail)) {
      // FastAPI validation errors arrive as a list of field problems.
      detail = body.detail
        .map((item) => {
          const entry = item as { loc?: unknown[]; msg?: string };
          const location = Array.isArray(entry.loc) ? entry.loc.slice(1).join('.') : '';
          return location ? `${location}: ${entry.msg}` : entry.msg;
        })
        .filter(Boolean)
        .join('; ');
    }
    requestId = body.request_id;
  } catch {
    // Body was not JSON; keep the status-based message.
  }
  throw new ApiError(detail, response.status, requestId);
}

/** Fetch from a server component. Never cached. */
export async function serverGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    return readError(response);
  }
  return (await response.json()) as T;
}

/**
 * Fetch from a server component, returning null instead of throwing.
 *
 * Used where a page should still render when the API is unreachable - the
 * layout can then show a clear "backend not running" state rather than an
 * error boundary, which is a far better first-run experience.
 */
export async function serverGetSafe<T>(path: string): Promise<T | null> {
  try {
    return await serverGet<T>(path);
  } catch {
    return null;
  }
}

export async function clientFetch<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const { json, ...rest } = init;
  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      Accept: 'application/json',
      ...(json !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(rest.headers ?? {}),
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (!response.ok) {
    return readError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

// -- server-side reads ------------------------------------------------------

export const getRuntime = () => serverGetSafe<RuntimeStatus>('/api/runtime');
export const getDashboard = () => serverGetSafe<DashboardData>('/api/dashboard');
export const getCases = () => serverGetSafe<{ cases: CaseSummary[] }>('/api/cases');
export const getCase = (caseId: string) => serverGetSafe<CaseDetail>(`/api/cases/${caseId}`);
export const getOperations = () => serverGetSafe<OperationsData>('/api/operations');
export const getArchitecture = () => serverGetSafe<ArchitectureData>('/api/architecture');
export const getGlobalAudit = () =>
  serverGetSafe<{ events: AuditEvent[] }>('/api/audit?limit=60');

export const getInvestigation = (caseId: string, investigationId: string) =>
  serverGetSafe<InvestigationDetail>(
    `/api/cases/${caseId}/investigations/${investigationId}`,
  );

export const getCaseAudit = (caseId: string) =>
  serverGetSafe<{ events: AuditEvent[] }>(`/api/cases/${caseId}/audit`);

export const getGraph = (investigationId: string) =>
  serverGetSafe<EvidenceGraphData>(`/api/investigations/${investigationId}/graph`);

export const getScenarioVariables = (investigationId: string) =>
  serverGetSafe<{ variables: ScenarioVariable[]; note: string }>(
    `/api/investigations/${investigationId}/scenario/variables`,
  );

export const getSuggestedQuestions = (investigationId: string) =>
  serverGetSafe<{ questions: string[] }>(
    `/api/investigations/${investigationId}/suggested-questions`,
  );

export const getLatestEvaluation = () =>
  serverGetSafe<{ run: EvalRun | null; history: unknown[]; message?: string }>(
    '/api/evaluation/latest',
  );

export const getEvaluationCases = () =>
  serverGetSafe<{
    total: number;
    requires_model: number;
    deterministic: number;
    by_category: Record<string, number>;
    cases: {
      id: string;
      category: string;
      description: string;
      requires_model: boolean;
      tags: string[];
    }[];
  }>('/api/evaluation/cases');

export const getValueCaseDefaults = () =>
  serverGetSafe<{
    assumptions: Record<string, number>;
    notes: Record<string, string>;
    disclaimer: string;
  }>('/api/value-case/defaults');

// -- client-side writes -----------------------------------------------------

export const runInvestigation = (caseId: string) =>
  clientFetch<InvestigationDetail>(`/api/cases/${caseId}/investigations`, {
    method: 'POST',
    json: { actor: 'analyst' },
  });

export const setSeverity = (
  investigationId: string,
  riskId: string,
  severity: string,
  rationale: string,
) =>
  clientFetch<{ finding: unknown; assessment: unknown }>(
    `/api/investigations/${investigationId}/findings/${riskId}/severity`,
    { method: 'PATCH', json: { severity, rationale, actor: 'analyst' } },
  );

export const setLikelihood = (
  investigationId: string,
  riskId: string,
  likelihood: string,
  rationale: string,
) =>
  clientFetch<{ finding: unknown; assessment: unknown }>(
    `/api/investigations/${investigationId}/findings/${riskId}/likelihood`,
    { method: 'PATCH', json: { likelihood, rationale, actor: 'analyst' } },
  );

export const markFalsePositive = (
  investigationId: string,
  riskId: string,
  rationale: string,
) =>
  clientFetch<{ finding: unknown; assessment: unknown }>(
    `/api/investigations/${investigationId}/findings/${riskId}/false-positive`,
    { method: 'POST', json: { rationale, actor: 'analyst' } },
  );

export const addNote = (investigationId: string, riskId: string, note: string) =>
  clientFetch<{ finding: unknown }>(
    `/api/investigations/${investigationId}/findings/${riskId}/note`,
    { method: 'POST', json: { note, actor: 'analyst' } },
  );

export const requestChallenge = (investigationId: string, riskId: string) =>
  clientFetch<{ challenges: unknown[]; model: string; replayed: boolean }>(
    `/api/investigations/${investigationId}/findings/${riskId}/challenge`,
    { method: 'POST' },
  );

export const submitReview = (
  investigationId: string,
  decision: string,
  comment: string,
) =>
  clientFetch<{ review: unknown; investigation: InvestigationDetail }>(
    `/api/investigations/${investigationId}/review`,
    { method: 'POST', json: { decision, comment, actor: 'analyst' } },
  );

export const askArgus = (investigationId: string, question: string) =>
  clientFetch<GroundedAnswer>(`/api/investigations/${investigationId}/ask`, {
    method: 'POST',
    json: { question, actor: 'analyst' },
  });

export const runScenario = (investigationId: string, variable: string, value: number) =>
  clientFetch<ScenarioResult>(`/api/investigations/${investigationId}/scenario`, {
    method: 'POST',
    json: { variable, value },
  });

export const runEvaluation = () =>
  clientFetch<{ run: EvalRun; history: unknown[] }>('/api/evaluation/run', {
    method: 'POST',
    json: {},
  });

export const computeValueCase = (assumptions: Record<string, number | string>) =>
  clientFetch<{
    result: ValueCaseResult;
    sensitivity: {
      variable: string;
      base_value: number;
      series: { value: number; annual_net_value: number; break_even_months: number | null }[];
    };
    notes: Record<string, string>;
  }>('/api/value-case', { method: 'POST', json: assumptions });

export const fetchReport = (caseId: string, investigationId: string) =>
  clientFetch<{
    title: string;
    reference: string;
    generated_at: string;
    sections: string[];
    markdown: string;
  }>(`/api/cases/${caseId}/investigations/${investigationId}/report`);

export const reportPdfUrl = (caseId: string, investigationId: string) =>
  `${API_BASE}/api/cases/${caseId}/investigations/${investigationId}/report.pdf`;
