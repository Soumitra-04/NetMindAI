import { apiClient } from './client';
import { TopologySnapshot } from './types';

export const topologyApi = {
  getTopology: (): Promise<TopologySnapshot> =>
    apiClient<TopologySnapshot>('/topology/', {
      method: 'GET',
    }),
};

