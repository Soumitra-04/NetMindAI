import { apiClient } from './client';
import {
  ExecutionResult,
  RecoveryRecommendation,
  SentinelReport,
  VerificationReport,
} from './types';

export interface DetectOptions {
  use_llm?: boolean;
  flow_features?: Record<string, unknown> | Array<Record<string, unknown>> | null;
}

export interface RecommendOptions {
  use_llm?: boolean;
  detection_report?: SentinelReport | null;
}

export interface ApprovalPayload {
  approver?: string;
  notes?: string;
}

export interface RejectionPayload {
  approver?: string;
  reason?: string;
}

export const blueApi = {
  detect: (options: DetectOptions = {}): Promise<SentinelReport> =>
    apiClient<SentinelReport>('/blue/sentinel/detect', {
      method: 'POST',
      params: { use_llm: options.use_llm ?? true },
      body: options.flow_features ? JSON.stringify(options.flow_features) : undefined,
    }),

  recommend: (options: RecommendOptions = {}): Promise<RecoveryRecommendation> =>
    apiClient<RecoveryRecommendation>('/blue/response/recommend', {
      method: 'POST',
      params: { use_llm: options.use_llm ?? true },
      body: options.detection_report ? JSON.stringify(options.detection_report) : undefined,
    }),

  listRecommendations: (statusFilter?: string): Promise<RecoveryRecommendation[]> =>
    apiClient<RecoveryRecommendation[]>('/blue/response/recommendations', {
      method: 'GET',
      params: statusFilter ? { status: statusFilter } : undefined,
    }),

  getRecommendation: (recommendationId: string): Promise<RecoveryRecommendation> =>
    apiClient<RecoveryRecommendation>(
      `/blue/response/recommendations/${encodeURIComponent(recommendationId)}`,
      {
        method: 'GET',
      }
    ),

  approve: (
    recommendationId: string,
    payload: ApprovalPayload = {}
  ): Promise<RecoveryRecommendation> =>
    apiClient<RecoveryRecommendation>(
      `/blue/response/recommendations/${encodeURIComponent(recommendationId)}/approve`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    ),

  reject: (
    recommendationId: string,
    payload: RejectionPayload = {}
  ): Promise<RecoveryRecommendation> =>
    apiClient<RecoveryRecommendation>(
      `/blue/response/recommendations/${encodeURIComponent(recommendationId)}/reject`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    ),

  execute: (recommendationId: string): Promise<ExecutionResult> =>
    apiClient<ExecutionResult>(
      `/blue/response/recommendations/${encodeURIComponent(recommendationId)}/execute`,
      {
        method: 'POST',
      }
    ),

  getVerification: (recommendationId: string): Promise<VerificationReport> =>
    apiClient<VerificationReport>(
      `/blue/response/recommendations/${encodeURIComponent(recommendationId)}/verification`,
      {
        method: 'GET',
      }
    ),
};

