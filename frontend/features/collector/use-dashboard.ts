/** 采集概览轮询 Hook，负责读取状态和请求生命周期。 */
import { useCallback, useEffect, useRef, useState } from "react";
import { readDashboard } from "./api";
import type { Dashboard } from "./types";

const POLL_INTERVAL_MS = 5000;

/** 管理概览数据、读取错误与轮询；同一时间只发一个请求，卸载时取消。 */
export function useDashboard() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const activeRequest = useRef<AbortController | null>(null);

  /** 串行读取最新概览，取消请求时不再更新组件状态。 */
  const refresh = useCallback(async () => {
    if (activeRequest.current) return;
    const controller = new AbortController();
    activeRequest.current = controller;
    setRefreshing(true);
    try {
      const dashboard = await readDashboard(controller.signal);
      if (controller.signal.aborted) return;
      setData(dashboard);
      setError("");
    } catch (error) {
      if (controller.signal.aborted) return;
      setError(error instanceof Error ? error.message : "无法连接管理服务");
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        if (!controller.signal.aborted) setRefreshing(false);
      }
    }
  }, []);

  // 安装首次加载与轮询；清理时取消定时器和未完成的网络请求。
  useEffect(() => {
    const initialRefresh = setTimeout(() => void refresh(), 0);
    const polling = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => {
      clearTimeout(initialRefresh);
      clearInterval(polling);
      activeRequest.current?.abort();
      activeRequest.current = null;
    };
  }, [refresh]);

  return { data, error, refreshing, refresh };
}
