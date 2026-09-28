/** 消息分页和刷新状态；只更新最新一页时不丢弃已经加载的历史记录。 */
import { useEffect, useRef, useState } from "react";
import { readMessages } from "./api";
import type { CollectedMessage, MessagePage } from "./types";

/** 按精确 Snowflake 合并重复消息并升序排序，避免大整数转 Number 后丢失精度。 */
function mergeMessages(current: CollectedMessage[], incoming: CollectedMessage[]) {
  const messages = new Map(current.map((message) => [message.message_id, message]));
  incoming.forEach((message) => messages.set(message.message_id, message));
  return [...messages.values()].sort((left, right) => {
    const first = BigInt(left.message_id),
      second = BigInt(right.message_id);
    if (first === second) return 0;
    return first < second ? -1 : 1;
  });
}

/** 管理一个固定频道的消息；父组件使用 key 在切换频道时隔离请求和状态。 */
export function useMessageFeed(channelId: string) {
  const [page, setPage] = useState<MessagePage | null>(null);
  const [error, setError] = useState("");
  const [loadingOlder, setLoadingOlder] = useState(false);
  const lifecycle = useRef<AbortController | null>(null);
  const olderRequest = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    lifecycle.current = controller;
    let timer: ReturnType<typeof setTimeout>;
    let newestId: string | undefined;
    /** 读取最近消息并保留历史页；刷新失败显示错误，不清空已有记录。 */
    async function poll() {
      try {
        const recent = await readMessages(channelId, controller.signal);
        // 两轮刷新之间超过一页时补齐中间消息，避免只合并最新 50 条造成缺口。
        let incoming = recent.messages;
        let cursor = recent.next_before;
        while (
          newestId &&
          cursor &&
          incoming.length &&
          BigInt(incoming[0].message_id) > BigInt(newestId)
        ) {
          const bridge = await readMessages(channelId, controller.signal, cursor);
          incoming = [...bridge.messages, ...incoming];
          cursor = bridge.next_before;
        }
        if (controller.signal.aborted) return;
        newestId = incoming.at(-1)?.message_id ?? newestId;
        setPage((previous) =>
          previous
            ? { ...previous, messages: mergeMessages(previous.messages, incoming) }
            : recent,
        );
        setError("");
      } catch (error) {
        if (controller.signal.aborted) return;
        setError(error instanceof Error ? error.message : "消息读取失败");
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 5000);
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
      lifecycle.current = null;
    };
  }, [channelId]);

  /** 使用当前历史游标翻页；并发请求互斥，切换频道后取消响应更新。 */
  async function loadOlder() {
    const controller = lifecycle.current;
    if (!page?.next_before || !controller || olderRequest.current) return;
    olderRequest.current = true;
    setLoadingOlder(true);
    try {
      const older = await readMessages(channelId, controller.signal, page.next_before);
      if (controller.signal.aborted) return;
      setPage((previous) => ({
        messages: mergeMessages(previous?.messages ?? [], older.messages),
        next_before: older.next_before,
      }));
      setError("");
    } catch (error) {
      if (!controller.signal.aborted)
        setError(error instanceof Error ? error.message : "历史消息读取失败");
    } finally {
      olderRequest.current = false;
      if (!controller.signal.aborted) setLoadingOlder(false);
    }
  }
  return { page, error, loadingOlder, loadOlder };
}
