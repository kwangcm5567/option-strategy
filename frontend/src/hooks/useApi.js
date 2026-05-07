import { useState, useEffect, useCallback, useRef } from 'react';

const _raw = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
export const API_BASE = _raw.startsWith('http') ? _raw : `https://${_raw}`;

export function useApi(endpoint, { timeout = 90_000 } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(!!endpoint);
  const [error, setError] = useState(null);
  const abortRef    = useRef(null);
  const loadingRef  = useRef(!!endpoint); // ref 版本供事件监听器读取

  const fetchData = useCallback(async (url) => {
    if (!url) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    loadingRef.current = true;
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
        setError('请求被中断。如刚从后台返回，请点击「刷新数据」重试。');
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
      loadingRef.current = false;
    }
  }, [timeout]);

  useEffect(() => {
    if (!endpoint) return;
    fetchData(endpoint);

    // 手机黑屏 / 切换 app 时浏览器会挂起 fetch 连接。
    // 页面重新可见且仍在 loading 时，自动重试一次。
    const onVisible = () => {
      if (document.visibilityState === 'visible' && loadingRef.current) {
        // 等 2 秒：给可能仍在传输的响应一个机会先到达
        setTimeout(() => {
          if (loadingRef.current) fetchData(endpoint);
        }, 2000);
      }
    };

    document.addEventListener('visibilitychange', onVisible);
    return () => {
      abortRef.current?.abort();
      document.removeEventListener('visibilitychange', onVisible);
    };
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
