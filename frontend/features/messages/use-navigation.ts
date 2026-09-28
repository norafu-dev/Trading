/** 轮询频道分组导航，保留用户当前选择，不把 API 错误当作空导航。 */
import { useEffect, useState } from "react";
import { readNavigation } from "./api";
import type { MessageNavigation } from "./types";

/** 安装定时读取并在卸载时取消请求；只在上一次请求完成后等待下一轮。 */
export function useNavigation() {
  const [data, setData] = useState<MessageNavigation | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    /** 获取导航后安排下一次请求，避免慢请求堆叠和卸载后更新状态。 */
    async function poll() {
      try {
        const navigation = await readNavigation(controller.signal);
        if (controller.signal.aborted) return;
        setData(navigation);
        setError("");
      } catch (error) {
        if (controller.signal.aborted) return;
        setError(error instanceof Error ? error.message : "导航加载失败");
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 5000);
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [revision]);
  /** 在分组或拖拽保存后立即重读导航，不等待下一次轮询。 */
  function refresh() {
    setRevision((value) => value + 1);
  }
  return { data, error, refresh };
}
