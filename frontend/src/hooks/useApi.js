import { useState, useEffect, useCallback, useRef } from 'react';

const _raw = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
export const API_BASE = _raw.startsWith('http') ? _raw : `https://${_raw}`;

export function useApi(endpoint, { timeout = 90_000 } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(!!endpoint);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);

  const fetchData = useCallback(async (url) => {
    if (!url) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    const timeoutId = setTimeout(() => controller.abort(), timeout);
    try {
      const res = await fetch(`${API_BASE}${url}`, { signal: controller.signal });
      clearTimeout(timeoutId);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `服务器返回错误 ${res.status}`);
      }
      const json = await res.json();
      setData(json);
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError') {
        setError('请求超时，后端正在处理数据（首次可能需要 60–90 秒），请稍后点击刷新重试。');
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, [timeout]);

  useEffect(() => {
    if (endpoint) fetchData(endpoint);
    return () => abortRef.current?.abort();
  }, [endpoint, fetchData]);

  const refetch = useCallback((overrideUrl) => {
    fetchData(overrideUrl || endpoint);
  }, [endpoint, fetchData]);

  return { data, loading, error, refetch };
}

export async function apiFetch(method, endpoint, body) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `请求失败 ${res.status}`);
  }
  return res.json();
}
