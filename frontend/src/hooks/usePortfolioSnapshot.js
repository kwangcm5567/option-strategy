import { useCallback, useEffect, useRef, useState } from 'react';
import { API_BASE } from './useApi';

/** @param {string} positionKey */
export default function usePortfolioSnapshot(positionKey) {
  const [state, setState] = useState({ key: '', data: null, loading: false, error: null });
  const requestRef = useRef(null);

  const refresh = useCallback(async (force = true) => {
    if (positionKey === '[]' || requestRef.current) return;
    const controller = new AbortController();
    requestRef.current = controller;
    setState(previous => ({ ...previous, loading: true, error: null }));
    const timeout = setTimeout(() => controller.abort(), 90_000);
    try {
      const response = await fetch(`${API_BASE}/api/portfolio/snapshot?force_refresh=${force}`, {
        signal: controller.signal, cache: 'no-store',
      });
      if (!response.ok) throw new Error(`行情接口返回 ${response.status}`);
      const data = await response.json();
      if (requestRef.current === controller && !controller.signal.aborted) {
        setState({ key: positionKey, data, loading: false, error: null });
      }
    } catch (error) {
      if (requestRef.current === controller) {
        setState({ key: positionKey, data: null, loading: false,
          error: error.name === 'AbortError' ? '行情请求超时，请重新刷新' : error.message });
      }
    } finally {
      clearTimeout(timeout);
      if (requestRef.current === controller) requestRef.current = null;
    }
  }, [positionKey]);

  useEffect(() => {
    const initial = setTimeout(() => refresh(false), 0);
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') refresh(false);
    }, 120_000);
    const resume = () => {
      if (document.visibilityState === 'visible') refresh(true);
    };
    document.addEventListener('visibilitychange', resume);
    window.addEventListener('focus', resume);
    return () => {
      clearTimeout(initial);
      clearInterval(interval);
      document.removeEventListener('visibilitychange', resume);
      window.removeEventListener('focus', resume);
      requestRef.current?.abort();
      requestRef.current = null;
    };
  }, [refresh]);

  return { snapshot: state.key === positionKey ? state.data : null,
    loading: state.loading, error: state.key === positionKey ? state.error : null, refresh };
}
