/** 频道分组编辑弹窗：新增、重命名或删除分组，频道本身不会被删除。 */
import { useState, type FormEvent } from "react";
import { FolderPlus, Trash2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { MessageGroup } from "./types";

/** 保存分组名称；编辑模式还允许删除分组并把频道移回未分组。 */
export function GroupEditor({
  group,
  onClose,
  onSave,
  onDelete,
}: {
  group: MessageGroup | null;
  onClose: () => void;
  onSave: (name: string) => Promise<void>;
  onDelete: (() => Promise<void>) | null;
}) {
  const [name, setName] = useState(group?.name ?? "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  /** 校验名称后调用父组件保存，失败时保留当前输入。 */
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      setError("请输入分组名称。");
      return;
    }
    setBusy(true);
    try {
      await onSave(name.trim());
    } catch (error) {
      setError(error instanceof Error ? error.message : "分组保存失败");
      setBusy(false);
    }
  }

  /** 删除分组；所属频道由服务端移回未分组区域。 */
  async function remove() {
    if (!onDelete) return;
    setBusy(true);
    try {
      await onDelete();
    } catch (error) {
      setError(error instanceof Error ? error.message : "分组删除失败");
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent showCloseButton={!busy}>
        <DialogHeader>
          <DialogTitle>{group ? "编辑频道分组" : "新建频道分组"}</DialogTitle>
          <DialogDescription>频道可在消息页拖入分组并调整顺序。</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="channel-group-name">分组名称</Label>
            <Input
              id="channel-group-name"
              value={name}
              maxLength={100}
              autoFocus
              onChange={(event) => setName(event.target.value)}
              placeholder="例如：美股 · 交易员"
            />
          </div>
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <DialogFooter className="justify-between sm:justify-between">
            {group ? (
              <Button
                type="button"
                variant="destructive"
                disabled={busy}
                onClick={remove}
              >
                <Trash2 />
                删除分组
              </Button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
                取消
              </Button>
              <Button type="submit" disabled={busy}>
                <FolderPlus />
                {busy ? "保存中…" : "保存分组"}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
