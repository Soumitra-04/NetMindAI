import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { healthApi } from '../api/health';

interface BackendStatusContextType {
  isConnected: boolean;
  isChecking: boolean;
  lastChecked: Date | null;
  error: string | null;
  checkConnection: () => Promise<boolean>;
}

const BackendStatusContext = createContext<BackendStatusContextType>({
  isConnected: false,
  isChecking: true,
  lastChecked: null,
  error: null,
  checkConnection: async () => false,
});

export const BackendStatusProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isChecking, setIsChecking] = useState<boolean>(true);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkConnection = useCallback(async (): Promise<boolean> => {
    setIsChecking(true);
    try {
      const res = await healthApi.check();
      const healthy = res.status === 'healthy';
      setIsConnected(healthy);
      setError(null);
      setLastChecked(new Date());
      return healthy;
    } catch (err: any) {
      setIsConnected(false);
      setError(err.message || 'Cannot reach backend API');
      setLastChecked(new Date());
      return false;
    } finally {
      setIsChecking(false);
    }
  }, []);

  useEffect(() => {
    checkConnection();
    // Periodic health check every 20 seconds
    const interval = setInterval(checkConnection, 20000);
    return () => clearInterval(interval);
  }, [checkConnection]);

  return (
    <BackendStatusContext.Provider
      value={{
        isConnected,
        isChecking,
        lastChecked,
        error,
        checkConnection,
      }}
    >
      {children}
    </BackendStatusContext.Provider>
  );
};

export const useBackendStatus = () => useContext(BackendStatusContext);

