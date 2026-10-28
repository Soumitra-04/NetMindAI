/**
 * TypeScript types strictly aligned with NetMind backend Pydantic models.
 */

export type DetectionStatus = 'healthy' | 'anomaly_detected' | 'investigation_required';

export type RecoveryActionType = 'restore_link' | 'restore_node' | 'no_action';

export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'executed' | 'cancelled';

export type VerificationStatus = 'verified_success' | 'partial_recovery' | 'verification_failed';

export type EventSeverity = 'debug' | 'info' | 'warning' | 'error' | 'critical';

export type OrchestrationStage =
  | 'initialized'
  | 'plan_disruption'
  | 'execute_disruption'
  | 'detect_anomaly'
  | 'evaluate_detection'
  | 'recommend_recovery'
  | 'validate_recommendation'
  | 'request_human_approval'
  | 'execute_recovery'
  | 'verify_recovery'
  | 'finalize_run'
  | 'completed';

export type OrchestrationStatus =
  | 'initialized'
  | 'running'
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'completed'
  | 'completed_healthy'
  | 'completed_no_action'
  | 'partial_success'
  | 'verification_failed'
  | 'failed';

export interface ModelInferenceStatus {
  status: 'unavailable' | 'completed' | 'error';
  reason?: string | null;
  result?: Record<string, unknown> | null;
}

export interface SentinelEvidence {
  inactive_nodes: Array<{ id: string; name: string; type: string }>;
  inactive_links: Array<{ source: string; target: string }>;
  unreachable_flows: Array<{ id: string; source: string; destination: string }>;
  contextual_events: Array<Record<string, unknown>>;
  metrics_summary: Record<string, unknown>;
}

export interface SentinelReport {
  detection_id: string;
  timestamp: string;
  status: DetectionStatus;
  findings: string[];
  affected_nodes: string[];
  affected_links: string[];
  affected_flows: string[];
  evidence: SentinelEvidence;
  severity: string;
  confidence: number;
  recommended_action: string;
  model_inference: ModelInferenceStatus;
  errors_or_limitations: string[];
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

export interface RecoveryRecommendation {
  recommendation_id: string;
  detection_id: string;
  action_type: RecoveryActionType;
  target?: string | null;
  reason: string;
  expected_effect: string;
  preconditions: string[];
  approval_required: boolean;
  approval_status: ApprovalStatus;
  validation_result: ValidationResult;
  created_at: string;
  approver?: string | null;
  approval_notes?: string | null;
}

export interface VerificationReport {
  status: VerificationStatus;
  target_active: boolean;
  route_after?: string[] | null;
  reachable_flows: number;
  details: Record<string, unknown>;
}

export interface ExecutionResult {
  recommendation_id: string;
  action_type: RecoveryActionType;
  target?: string | null;
  execution_status: string;
  verification: VerificationReport;
  timestamp: string;
}

export interface NetworkNode {
  id: string;
  name: string;
  type: 'host' | 'router' | 'switch' | 'server' | 'firewall';
  ip_address?: string | null;
  active: boolean;
  metadata: Record<string, unknown>;
}

export interface NetworkLink {
  source: string;
  target: string;
  latency_ms: number;
  bandwidth_mbps: number;
  packet_loss_pct: number;
  active: boolean;
  metadata: Record<string, unknown>;
}

export interface TopologySnapshot {
  nodes: NetworkNode[];
  links: NetworkLink[];
}

export interface TrafficFlow {
  id: string;
  source: string;
  destination: string;
  protocol: string;
  packets_per_second: number;
  packet_size_bytes: number;
  offered_mbps: number;
  path_latency_ms?: number | null;
  active: boolean;
  reachable: boolean;
}

export interface SimulationMetrics {
  timestamp: string;
  topology: {
    total_nodes: number;
    active_nodes: number;
    total_links: number;
    active_links: number;
  };
  traffic: {
    total_flows: number;
    active_flows: number;
    reachable_active_flows: number;
    total_offered_mbps: number;
    average_path_latency_ms?: number | null;
  };
  limitations: string[];
}

export interface SimulationSnapshot {
  step_number: number;
  topology: TopologySnapshot;
  flows: TrafficFlow[];
  metrics: SimulationMetrics;
}

export interface NetworkEvent {
  id: string;
  timestamp: string;
  event_type: string;
  severity: EventSeverity;
  source: string;
  entity_id?: string | null;
  message: string;
  details: Record<string, unknown>;
}

export interface OrchestrationStartRequest {
  goal?: string;
  scenario_id?: string | null;
  skip_disruption?: boolean;
  use_llm?: boolean;
}

export interface OrchestrationResumeRequest {
  decision: 'approve' | 'reject';
  recommendation_id: string;
  approver?: string;
  notes?: string;
}

export interface OrchestrationRunResponse {
  run_id: string;
  status: OrchestrationStatus;
  stage: OrchestrationStage;
  goal: string;
  pending_approval: boolean;
  scenario_id?: string | null;
  skip_disruption?: boolean;
  red_plan?: {
    scenario_id?: string;
    rationale?: string;
    planner_model?: string;
  } | null;
  disruption_result?: {
    scenario_id?: string;
    status?: string;
    action?: string;
    target?: string;
    route_before?: string[] | null;
    route_after?: string[] | null;
    disruption_active?: boolean;
    simulation_step?: number;
  } | null;
  sentinel_report?: SentinelReport | null;
  recommendation?: RecoveryRecommendation | null;
  recommendation_id?: string | null;
  approval_status?: string | null;
  approver?: string | null;
  recovery_executed: boolean;
  recovery_result?: ExecutionResult | null;
  verification_report?: VerificationReport | null;
  error?: string | null;
  failure_stage?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
}
