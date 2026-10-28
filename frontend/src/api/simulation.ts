import { apiClient } from './client';
import { SimulationSnapshot } from './types';

export const simulationApi = {
  getState: (): Promise<SimulationSnapshot> =>
    apiClient<SimulationSnapshot>('/simulation/state', {
      method: 'GET',
    }),

  step: (): Promise<SimulationSnapshot> =>
    apiClient<SimulationSnapshot>('/simulation/step', {
      method: 'POST',
    }),

  reset: (): Promise<SimulationSnapshot> =>
    apiClient<SimulationSnapshot>('/simulation/reset', {
      method: 'POST',
    }),
};

