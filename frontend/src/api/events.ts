import { apiClient } from './client';
import { NetworkEvent } from './types';

export interface GetEventsParams {
  limit?: number;
  severity?: string;
  event_type?: string;
}

export const eventsApi = {
  getEvents: (params?: GetEventsParams): Promise<NetworkEvent[]> =>
    apiClient<NetworkEvent[]>('/events/', {
      method: 'GET',
      params: {
        limit: params?.limit ?? 100,
        severity: params?.severity,
        event_type: params?.event_type,
      },
    }),
};

