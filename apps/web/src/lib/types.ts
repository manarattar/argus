/**
 * Types mirroring the API payloads in `apps/api/argus_api/serializers.py`.
 *
 * Hand-written rather than generated: the API surface is small and stable, and
 * a hand-written type can carry the documentation that matters - notably which
 * fields hold the AI's original recommendation versus the current value after a
 * human edit.
 */

export type RiskLevel = 'low' | 'moderate' | 'elevated' | 'high';
export type EvidenceStrength = 'strong' | 'moderate' | 'weak' | 'insufficient';
export type Severity = 'negligible' | 'minor' | 'moderate' | 'major' | 'severe';
export type Likelihood = 'rare' | 'unlikely' | 'possible' | 'likely' | 'almost_certain';
export type SupportStatus =
  | 'supported'
  | 'partially_supported'
  | 'unsupported'
  | 'conflicting';
export type CoverageStatus = 'complete' | 'partial' | 'missing';
export type StepStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'retried' | 'skipped';
export type TriggerType =
  | 'review_trigger'
  | 'potential_breach'
  | 'informational'
  | 'threshold_met';

export interface RuntimeStatus {
  mode: 'demo' | 'live';
  headline: string;
  explanation: string;
  backend: string;
  model: string;
  live: boolean;
  environment: string;
  database: string;
  count?: number;
  embedding: {
    name: string;
    description: string;
    semantic: boolean;
    dimensions: number;
    caveat: string | null;
  };
}

export interface ScoreFactor {
  key: string;
  label: string;
  detail: string;
  contribution: number;
  direction: 'increases' | 'decreases' | 'neutral';
}

export interface CoverageItem {
  category: string;
  category_label?: string;
  status: CoverageStatus;
  expected: string;
  found_evidence_ids: string[];
  note: string;
}

export interface EvidenceItem {
  evidence_id: string;
  statement: string;
  quote: string;
  kind: 'fact' | 'interpretation';
  category: string;
  category_label: string;
  document_id: string;
  document_name: string;
  section_reference: string;
  chunk_id: string;
  materiality: Severity;
  grounding_score: number;
  is_grounded: boolean;
}

export interface PolicyMatch {
  match_id: string;
  risk_id: string;
  policy_id: string;
  clause_reference: string;
  clause_title: string;
  relevance: string;
  trigger_type: TriggerType;
  threshold_assessment: string;
  sufficiency_caveat: string;
}

export interface Challenge {
  challenge_id: string;
  risk_id: string;
  challenge_type: string;
  challenge_type_label: string;
  argument: string;
  counter_evidence_ids: string[];
  suggested_revision: string;
  proposed_severity: string;
  unresolved: boolean;
  on_demand: boolean;
  created_at: string;
}

export interface Verification {
  verification_id: string;
  risk_id: string;
  claim: string;
  status: SupportStatus;
  status_label: string;
  reasoning: string;
  citations_checked: string[];
  irrelevant_citation_ids: string[];
  downgrade_recommended: boolean;
}

export interface Override {
  id: string;
  risk_id: string;
  field: string;
  /** What the system recommended. Never overwritten. */
  ai_value: string;
  /** What the analyst decided instead. */
  human_value: string;
  rationale: string;
  actor: string;
  created_at: string;
}

export interface RiskFinding {
  risk_id: string;
  title: string;
  category: string;
  category_label: string;
  description: string;
  /** Current effective values, after any human edit. */
  severity: Severity;
  severity_label: string;
  likelihood: Likelihood;
  likelihood_label: string;
  /** The system's original recommendation, preserved for comparison. */
  ai_severity: Severity;
  ai_likelihood: Likelihood;
  was_overridden: boolean;
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  assumptions: string[];
  open_questions: string[];
  mitigating_factors: string[];
  evidence_strength: EvidenceStrength;
  evidence_strength_label: string;
  strength_rationale: string;
  inherent_score: number;
  adjusted_score: number;
  mind_changer_increase: string;
  mind_changer_decrease: string;
  is_false_positive: boolean;
  analyst_note: string;
  verification: Verification | null;
  policy_matches: PolicyMatch[];
  challenges: Challenge[];
  overrides: Override[];
}

export interface InvestigationStep {
  step_id: string;
  ordinal: number;
  name: string;
  capability: string;
  status: StepStatus;
  summary: string;
  detail: Record<string, unknown>;
  prompt_reference: string;
  model: string;
  attempts: number;
  retries: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  duration_ms: number;
  replayed: boolean;
  error: string;
  started_at: string;
}

export interface Narrative {
  executive_summary?: string;
  key_judgements?: string[];
  limitations?: string[];
  recommended_followup?: string[];
  mind_changers?: { risk_id: string; would_increase: string; would_decrease: string }[];
}

export interface InvestigationSummary {
  id: string;
  case_id: string;
  /** Present on dashboard listings, which join the case for display. */
  reference?: string;
  organisation?: string;
  status: string;
  overall_level: RiskLevel | '';
  overall_level_label: string;
  overall_score: number;
  evidence_strength: EvidenceStrength | '';
  evidence_strength_label: string;
  findings: number;
  evidence_count: number;
  escalation_reasons: string[];
  demo_mode: boolean;
  model_name: string;
  duration_ms: number;
  estimated_cost_usd: number;
  started_at: string;
  completed_at: string | null;
  has_errors: boolean;
}

export interface InvestigationDetail extends InvestigationSummary {
  domain_key: string;
  model_backend: string;
  embedding_model: string;
  retrieval_quality: number;
  score_factors: ScoreFactor[];
  category_levels: Record<string, RiskLevel>;
  coverage: CoverageItem[];
  narrative: Narrative;
  integrity: { summary?: string; [key: string]: unknown };
  rejected_evidence: {
    evidence_id: string;
    statement: string;
    reason: string;
    grounding_score: number;
    cited_chunk_id: string;
  }[];
  errors: string[];
  tokens: { input: number; output: number };
  risks: RiskFinding[];
  evidence: EvidenceItem[];
  policy_matches: PolicyMatch[];
  challenges: Challenge[];
  verifications: Verification[];
  overrides: Override[];
  reviews: ReviewRecord[];
  steps: InvestigationStep[];
}

export interface ReviewRecord {
  id: string;
  decision: string;
  comment: string;
  actor: string;
  ai_overall_level: string;
  final_overall_level: string;
  changed_overall_level: boolean;
  created_at: string;
}

export interface CaseSummary {
  id: string;
  reference: string;
  organisation: string;
  review_type: string;
  domain_key: string;
  status: string;
  analyst: string;
  sector: string;
  jurisdiction: string;
  background: string;
  created_at: string;
  updated_at: string;
  document_count: number;
  latest_investigation: InvestigationSummary | null;
}

export interface CaseDetail extends CaseSummary {
  documents: DocumentSummary[];
  investigations: InvestigationSummary[];
}

export interface DocumentSummary {
  id: string;
  name: string;
  doc_kind: string;
  code: string;
  description: string;
  is_synthetic: boolean;
  characters: number;
  chunks: number;
}

export interface AuditEvent {
  id: string;
  case_id: string;
  investigation_id: string;
  actor: string;
  actor_type: 'human' | 'ai' | 'system';
  action: string;
  entity_type: string;
  entity_id: string;
  summary: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  created_at: string;
}

export interface DashboardData {
  cases: { total: number; active: number; awaiting_review: number };
  investigations: { total: number; completed: number; failed: number; demo_mode: number };
  average_investigation_ms: number;
  human_override_rate: number;
  evidence_coverage: number;
  estimated_cost_usd: number;
  cost_is_estimate: boolean;
  risk_distribution: Record<string, number>;
  attention: {
    case_id: string;
    investigation_id: string;
    reference: string;
    organisation: string;
    status: string;
    overall_level: string;
    reason: string;
    escalations: string[];
  }[];
  recent: InvestigationSummary[];
  system_health: {
    steps_executed: number;
    failed_steps: number;
    retried_steps: number;
    success_rate: number;
    schema_retry_rate: number;
  };
  runtime: RuntimeStatus;
}

export interface GraphNode {
  id: string;
  kind: 'assessment' | 'risk' | 'evidence' | 'document' | 'policy' | 'challenge';
  label: string;
  sublabel: string;
  weight: number;
  meta: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  weight: number;
}

export interface EvidenceGraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  counts: Record<string, number>;
}

export interface ScenarioVariable {
  key: string;
  label: string;
  unit: string;
  description: string;
  policy_reference: string;
  current_value: number;
  minimum: number;
  maximum: number;
  step: number;
  source: string;
  affects: string[];
}

export interface ScenarioResult {
  variable: string;
  original_value: number;
  scenario_value: number;
  original_level: RiskLevel;
  original_score: number;
  scenario_level: RiskLevel;
  scenario_score: number;
  changed_findings: {
    risk_id: string;
    title: string;
    category: string;
    original_severity: string;
    scenario_severity: string;
    original_likelihood: string;
    scenario_likelihood: string;
    explanation: string;
  }[];
  unaffected_count: number;
  factors: ScoreFactor[];
  explanation: string;
  disclaimer: string;
}

export interface EvalCaseResult {
  case_id: string;
  category: string;
  description: string;
  passed: boolean;
  score: number;
  expected: string;
  actual: string;
  detail: Record<string, unknown>;
  error: string;
  duration_ms: number;
  status: 'passed' | 'failed' | 'skipped' | 'error';
}

export interface EvalCategoryMetrics {
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  pass_rate: number | null;
  mean_score: number | null;
}

export interface EvalRun {
  id: string;
  suite: string;
  created_at: string;
  model_backend: string;
  model_name: string;
  embedding_model: string;
  demo_mode: boolean;
  total_cases: number;
  passed: number;
  failed: number;
  skipped_or_errored: number;
  duration_ms: number;
  metrics: {
    total_cases: number;
    executed: number;
    passed: number;
    failed: number;
    skipped: number;
    errored: number;
    pass_rate: number | null;
    coverage: number;
    mean_score: number | null;
    by_category: Record<string, EvalCategoryMetrics>;
    duration_ms: number;
    context: Record<string, unknown>;
  };
  results: EvalCaseResult[];
}

export interface OperationsData {
  totals: {
    investigations: number;
    steps: number;
    llm_calls: number;
    input_tokens: number;
    output_tokens: number;
    estimated_cost_usd: number;
    failed_steps: number;
    retries: number;
    replayed_steps: number;
  };
  by_capability: {
    capability: string;
    executions: number;
    failures: number;
    retries: number;
    avg_duration_ms: number;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
  }[];
  overrides: {
    total_findings: number;
    findings_overridden: number;
    override_rate: number;
    overrides_by_field: Record<string, number>;
    reviews_submitted: number;
    reviews_changing_overall_level: number;
    decisions: Record<string, number>;
  };
  category_distribution: { category: string; count: number }[];
  health: DashboardData['system_health'];
  grounding: {
    evidence_proposed: number;
    evidence_grounded: number;
    evidence_rejected: number;
    rejection_rate: number;
    mean_grounding_score: number;
  };
  latest_evaluation: {
    id: string;
    created_at: string;
    passed: number;
    failed: number;
    total: number;
    metrics: Record<string, unknown>;
  } | null;
  runtime: RuntimeStatus;
  trace_policy: string;
  cost_is_estimate: boolean;
}

export interface ValueCaseResult {
  monthly_manual_hours: number;
  monthly_assisted_hours: number;
  monthly_hours_saved: number;
  hours_saved_per_case: number;
  monthly_capacity_value: number;
  monthly_ai_cost: number;
  monthly_run_cost: number;
  monthly_net_value: number;
  annual_net_value: number;
  break_even_months: number | null;
  additional_cases_capacity: number;
  effective_cases: number;
  assumptions: Record<string, number>;
  disclaimer: string;
}

export interface ArchitectureData {
  runtime: RuntimeStatus;
  layers: { key: string; name: string; detail: string }[];
  capabilities: { key: string; name: string; reusable: boolean; prompt: string }[];
  domains: {
    key: string;
    name: string;
    description: string;
    status: 'implemented' | 'design';
    implemented: boolean;
    risk_categories: string[];
    policy_library: string[];
    expected_evidence: { key: string; label: string; required: boolean }[];
    escalation_rules: { key: string; label: string; description: string }[];
  }[];
  prompts: {
    library_version: string;
    prompts: { id: string; version: string; reference: string }[];
  };
  controls: { name: string; kind: string; detail: string }[];
  operations: OperationsData['totals'];
}

export interface GroundedAnswer {
  answer: string;
  answerable: boolean;
  insufficient_evidence_note: string;
  citations: {
    evidence_id: string;
    document_name: string;
    section_reference: string;
    quote: string;
  }[];
  model: string;
  replayed: boolean;
  estimated_cost_usd: number;
  latency_ms: number;
}
