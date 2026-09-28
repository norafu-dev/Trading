/** 来源移除确认弹窗，统一使用 shadcn Dialog，替代浏览器原生 confirm。 */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import type { Source } from "./types";

/** 展示待移除来源及数据保留范围；失败保持弹窗以便重试，提交期间禁止关闭。 */
export function SourceDeleteDialog({
  source,
  onClose,
  onDelete,
}: {
  source: Source;
  onClose: () => void;
  onDelete: (source: Source) => Promise<void>;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  /** 仅在没有删除请求进行时响应 Escape、遮罩和关闭按钮。 */
  function handleOpenChange(open: boolean) {
    if (!open && !pending) onClose();
  }

  /** 执行已确认的删除，捕获失败并允许再次提交；成功关闭由父组件负责。 */
  async function confirmRemoval() {
    setPending(true);
    setError("");
    try {
      await onDelete(source);
    } catch (error) {
      setError(error instanceof Error ? error.message : "移除失败");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open onOpenChange={handleOpenChange}>
      <DialogContent showCloseButton={!pending}>
        <DialogHeader>
          <DialogTitle>移除采集来源？</DialogTitle>
          <DialogDescription>
            将移除「{source.name}」的采集配置。已采集的历史消息会保留。
          </DialogDescription>
        </DialogHeader>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <DialogFooter>
          <Button variant="outline" disabled={pending} onClick={onClose}>
            取消
          </Button>
          <Button variant="destructive" disabled={pending} onClick={confirmRemoval}>
            {pending ? "移除中…" : "确认移除"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
