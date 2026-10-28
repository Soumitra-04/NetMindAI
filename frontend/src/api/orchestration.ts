import { apiClient } from './client';
import {
  OrchestrationResumeRequest,
  OrchestrationRunResponse,
  OrchestrationStartRequest,
} from './types';

export const orchestrationApi = {
  startRun: (request: OrchestrationStartRequest = {}): Promise<OrchestrationRunResponse> =>
    apiClient<OrchestrationRunResponse>('/orchestration/runs', {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  listRuns: (statusFilter?: string): Promise<OrchestrationRunResponse[]> =>
    apiClient<OrchestrationRunResponse[]>('/orchestration/runs', {
      method: 'GET',
      params: statusFilter ? { status: statusFilter } : undefined,
    }),

  getRun: (runId: string): Promise<OrchestrationRunResponse> =>
    apiClient<OrchestrationRunResponse>(`/orchestration/runs/${encodeURIComponent(runId)}`, {
      method: 'GET',
    }),

  resumeRun: (
    runId: string,
    request: OrchestrationResumeRequest
  ): Promise<OrchestrationRunResponse> =>
    apiClient<OrchestrationRunResponse>(
      `/orchestration/runs/${encodeURIComponent(runId)}/resume`,
      {
        method: 'POST',
        body: JSON.stringify(request),
      }
    ),

  getVerification: (runId: string): Promise<Record<string, unknown>> =>
    apiClient<Record<string, unknown>>(
      `/orchestration/runs/${encodeURIComponent(runId)}/verification`,
      {
        method: 'GET',
      }
    ),
};

