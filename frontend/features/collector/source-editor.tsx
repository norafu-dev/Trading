/** 来源新增与编辑表单；使用 shadcn Dialog 管理焦点、遮罩和键盘交互。 */
import { useState, type FormEvent } from "react";
import { RefreshCw, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import type { Source, SourceBody } from "./types";

/** 以传入来源回填表单；提交失败保留输入，保存期间禁止关闭和重复提交。 */
export function SourceEditor({
  source,
  onClose,
  onSave,
}: {
  source: Source | null;
  onClose: () => void;
  onSave: (body: SourceBody) => Promise<void>;
}) {
  const [name, setName] = useState(source?.name || "");
  const [kolName, setKolName] = useState(source?.kol_name || "");
  const [channel, setChannel] = useState(source?.channel_id || "");
  const [authors, setAuthors] = useState(source?.author_ids.join("\n") || "");
  const [enabled, setEnabled] = useState(source?.enabled ?? true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  /** 接收 Dialog 的关闭请求；保存中忽略 Escape、遮罩和关闭按钮触发的请求。 */
  function handleOpenChange(open: boolean) {
    if (!open && !saving) onClose();
  }

  /** 校验并去重输入后调用保存；失败以表单错误展示，不丢弃用户已填内容。 */
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    const ids = [...new Set(authors.split(/[\s,，;；]+/).filter(Boolean))];
    if (
      !name.trim() ||
      !kolName.trim() ||
      !/^[1-9][0-9]{0,19}$/.test(channel.trim()) ||
      !ids.length ||
      ids.length > 50 ||
      ids.some((id) => !/^[1-9][0-9]{0,19}$/.test(id))
    ) {
      setError("请填写频道名称、KOL 名字、有效的频道 ID，以及 1–50 个作者 ID。");
      return;
    }
    setSaving(true);
    try {
      await onSave({
        name: name.trim(),
        kol_name: kolName.trim(),
        group_id: source?.group_id ?? null,
        position: source?.position ?? 0,
        channel_id: channel.trim(),
        author_ids: ids,
        enabled,
      });
    } catch (error) {
      setError(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open onOpenChange={handleOpenChange}>
      <DialogContent showCloseButton={!saving} className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{source ? "编辑采集来源" : "添加采集来源"}</DialogTitle>
          <DialogDescription>
            选择一个频道或 Thread，开始积累 Trader 的真实消息。
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-5">
          {/* 简单输入回调只同步当前字段；格式校验统一在提交边界进行。 */}
          <div className="space-y-2">
            <Label htmlFor="source-name">频道名称</Label>
            <Input
              id="source-name"
              required
              maxLength={100}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="例如：Trader-Gauls"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="source-kol-name">KOL 名字</Label>
            <Input
              id="source-kol-name"
              required
              maxLength={100}
              value={kolName}
              onChange={(event) => setKolName(event.target.value)}
              placeholder="例如：Dr. Profit"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="source-channel">频道 / Thread ID</Label>
            <Input
              id="source-channel"
              required
              inputMode="numeric"
              maxLength={20}
              value={channel}
              onChange={(event) => setChannel(event.target.value)}
              placeholder="粘贴 Discord 频道或 Thread ID"
              aria-describedby="channel-hint"
            />
            <p id="channel-hint" className="text-xs text-muted-foreground">
              填写实际消息所在位置的 ID；父频道不自动包含子 Thread。
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="source-authors">Trader 作者 ID</Label>
            <Textarea
              id="source-authors"
              required
              value={authors}
              onChange={(event) => setAuthors(event.target.value)}
              placeholder="每行一个作者 ID，也可以用逗号分隔"
              rows={3}
              aria-describedby="authors-hint"
            />
            <p id="authors-hint" className="text-xs text-muted-foreground">
              只采集这些作者的消息，不按交易关键词过滤。
            </p>
          </div>
          <div className="flex items-start gap-3 rounded-lg bg-muted p-3">
            <Checkbox
              id="source-enabled"
              checked={enabled}
              onCheckedChange={(checked) => setEnabled(checked === true)}
            />
            <div className="space-y-1">
              <Label htmlFor="source-enabled">保存后启用此来源</Label>
              <p className="text-xs text-muted-foreground">
                Collector 连接后会验证权限并自动加载。
              </p>
            </div>
          </div>
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <DialogFooter>
            <Button variant="outline" type="button" disabled={saving} onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? <RefreshCw className="animate-spin" /> : <Check />}
              {saving ? "保存中…" : "保存来源"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
