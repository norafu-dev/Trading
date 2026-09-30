/** 采集面板客户端入口：协调轮询、来源操作和编辑/删除弹窗，布局仅面向 PC。 */
"use client";

import { useEffect, useState } from "react";
import { ChevronRight, Plus, CircleHelp, RefreshCw, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import type { Source, SourceBody, EditorState } from "./types";
import { states, time, connectionStatus, badgeVariant } from "./presentation";
import { saveSource, deleteSource } from "./api";
import { useDashboard } from "./use-dashboard";
import { SourceEditor } from "./source-editor";
import { SourceDeleteDialog } from "./source-delete-dialog";
import { Overview } from "./overview";
import { SourcesPanel } from "./sources-panel";
import { RuntimePanel } from "./runtime-panel";
import { EventsPanel } from "./events-panel";
import { MessagesPanel } from "./messages-panel";
import { StoragePanel } from "./storage-panel";
import { RecoveryPanel } from "./recovery-panel";

/** 组合业务区域；请求读取错误和单次操作错误分别管理，避免误报 Collector 离线。 */
export function CollectorDashboard() {
  const { data, error, refreshing, refresh } = useDashboard();
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const [query, setQuery] = useState("");
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [sourceToRemove, setSourceToRemove] = useState<Source | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // 成功提示自动消失；提示变化或组件卸载时取消上一轮定时器。
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 5000);
    return () => clearTimeout(timer);
  }, [notice]);
  const connection = connectionStatus(Boolean(data), error);
  const status = error
    ? { label: "状态未知", tone: "red", hint: "管理服务不可达，暂时无法确认采集状态。" }
    : states[data?.runtime.state || "stopped"] || states.stopped;

  /** 创建或更新当前编辑的来源；失败交给表单展示，成功后关闭弹窗并刷新。 */
  async function save(body: SourceBody) {
    if (!editor) return;
    await saveSource(body, editor.mode === "edit" ? editor.source.id : undefined);
    setEditor(null);
    setActionError("");
    setNotice("来源已保存，Collector 连接后会自动同步配置");
    await refresh();
  }

  /** 切换来源启用状态；失败保留原始服务端状态，不将失败操作伪装成成功。 */
  async function toggle(source: Source) {
    setBusy(source.id);
    setActionError("");
    try {
      await saveSource(
        {
          name: source.name,
          kol_name: source.kol_name,
          group_id: source.group_id,
          position: source.position,
          channel_id: source.channel_id,
          author_ids: source.author_ids,
          enabled: !source.enabled,
        },
        source.id,
      );
      setNotice(
        source.enabled
          ? "来源已停用，配置将在下一次同步生效"
          : "来源已启用，等待 Collector 校验",
      );
      await refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "更新失败");
    } finally {
      setBusy(null);
    }
  }

  /** 删除已确认来源；失败由确认弹窗处理，成功后刷新列表，历史消息由服务端保留。 */
  async function remove(source: Source) {
    setBusy(source.id);
    try {
      await deleteSource(source.id);
      setSourceToRemove(null);
      setActionError("");
      setNotice("来源已移除，历史消息已保留");
      await refresh();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="min-w-0 flex-1">
      <header className="flex h-16 items-center justify-between border-b bg-card px-8 text-sm">
        <div className="flex items-center gap-3 text-muted-foreground">
          工作台
          <ChevronRight className="size-3" />
          <span className="text-foreground">消息采集</span>
        </div>
        <Badge variant={badgeVariant(connection.tone)}>{connection.label}</Badge>
      </header>
      <main id="overview" className="mx-auto max-w-[1600px] space-y-6 p-8">
        {/* 编辑模式通过联合类型表达；简单事件回调只修改弹窗的打开状态。 */}
        <div className="flex items-center justify-between">
          <div>
            <p className="mb-2 text-xs tracking-[0.2em] text-muted-foreground">
              DISCORD INGESTION
            </p>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold">消息采集</h1>
              <Badge variant="secondary">MVP · 阶段 01</Badge>
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              管理 Trader 的消息来源，关注每一次采集的运行状态。
            </p>
          </div>
          <Button onClick={() => setEditor({ mode: "create" })}>
            <Plus />
            添加来源
          </Button>
        </div>
        {error && (
          <Alert variant="destructive">
            <CircleHelp />
            <AlertTitle>无法读取管理服务状态</AlertTitle>
            <AlertDescription>
              <p>{error}。数据可能已过期，请恢复连接后再操作。</p>
              <Button size="sm" variant="outline" onClick={() => void refresh()}>
                重试
              </Button>
            </AlertDescription>
          </Alert>
        )}
        {actionError && (
          <Alert variant="destructive">
            <AlertTitle>来源操作失败</AlertTitle>
            <AlertDescription>{actionError}</AlertDescription>
          </Alert>
        )}
        {data && !error && data.runtime.state !== "connected" && (
          <Alert>
            <CircleHelp />
            <AlertTitle>{status.label}</AlertTitle>
            <AlertDescription>
              <p>{status.hint}</p>
              {data.runtime.state === "missing_token" && (
                <p>
                  在项目 .env 中设置 DISCORD_TOKEN，再执行 make collect。Token
                  不会通过面板传输。
                </p>
              )}
            </AlertDescription>
          </Alert>
        )}
        <Overview data={data} status={status} />
        <SourcesPanel
          data={data}
          query={query}
          setQuery={setQuery}
          busy={busy}
          onEdit={(source) => setEditor({ mode: "edit", source })}
          onCreate={() => setEditor({ mode: "create" })}
          toggle={toggle}
          remove={setSourceToRemove}
        />
        <div className="grid grid-cols-2 items-start gap-6">
          <RuntimePanel data={data} error={error} />
          <EventsPanel data={data} error={error} />
        </div>
        <StoragePanel data={data} error={error} refresh={refresh} />
        <RecoveryPanel data={data} error={error} />
        <MessagesPanel data={data} />
        <footer className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Signal Desk / 消息先留存，策略后定义</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void refresh()}
            disabled={refreshing}
          >
            <RefreshCw className={refreshing ? "animate-spin" : ""} />
            {data ? `最近刷新 ${time(data.server_time)}` : "刷新状态"}
          </Button>
        </footer>
      </main>
      {notice && (
        <div className="fixed right-6 bottom-6 z-50 w-auto max-w-lg" role="status">
          <Alert className="border-primary/30 shadow-lg">
            <Check />
            <AlertDescription className="text-foreground">{notice}</AlertDescription>
          </Alert>
        </div>
      )}
      {editor && (
        <SourceEditor
          source={editor.mode === "create" ? null : editor.source}
          onClose={() => setEditor(null)}
          onSave={save}
        />
      )}
      {sourceToRemove && (
        <SourceDeleteDialog
          source={sourceToRemove}
          onClose={() => setSourceToRemove(null)}
          onDelete={remove}
        />
      )}
    </div>
  );
}
