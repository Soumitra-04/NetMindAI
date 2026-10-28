import { apiClient } from './client';

export interface HealthResponse {
  status: string;
}

export const healthApi = {
  check: (): Promise<HealthResponse> =>
    apiClient<HealthResponse>('/health', {
      method: 'GET',
    }),
};

