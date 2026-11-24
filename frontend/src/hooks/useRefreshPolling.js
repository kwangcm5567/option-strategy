import { useEffect } from 'react';

const POLL_MS = 10_000;

/** 后端返回 refreshing: true 时（正在后台重扫），静默轮询直到新结果落地。 */
export function useRefreshPolling(data, error, endpoint, refetch) {
  useEffect(() => {
    if (!data?.refreshing || error) return;
    const id = setTimeout(() => refetch(endpoint, { silent: true }), POLL_MS);
    return () => clearTimeout(id);
  }, [data, error, endpoint, refetch]);
}
