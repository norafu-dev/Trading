/** 图片归档的容量、状态及手动重试面板，复用概览轮询与 shadcn 基础控件。 */
import { useState } from "react";
import { HardDrive, RefreshCw } from "lucide-react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardAction,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { Dashboard } from "./types";
import { request } from "./api";

/** 采用十进制单位显示对象大小，与容量预警配置保持一致。 */
function bytesLabel(bytes: number) {
  return bytes >= 1_000_000_000
    ? `${(bytes / 1_000_000_000).toFixed(2)} GB`
    : `${(bytes / 1_000_000).toFixed(1)} MB`;
}

/** 明确区分未配置、已填写配置与已成功归档，不把前端在线当作 R2 正常。 */
export function StoragePanel({
  data,
  error,
  refresh,
}: {
  data: Dashboard | null;
  error: string;
  refresh: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const storage = data?.storage;
  let configurationLabel = "状态未知";
  if (storage && !error) {
    configurationLabel = storage.configured ? "R2 已配置" : "R2 待配置";
  }

  /** 主动重新排队失败图片，服务端确认后刷新；已有成功图片不重复上传。 */
  async function retry() {
    setBusy(true);
    setNotice("");
    try {
      const response = await request("media/retry", "POST");
      const result: { retried: number } = await response.json();
      setNotice(`已重新排队 ${result.retried} 张图片`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "重试失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card id="storage">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <HardDrive className="size-5" />
          图片归档
        </CardTitle>
        <CardDescription>原图保留在 R2 · 按内容去重 · 暂不自动删除</CardDescription>
        <CardAction>
          <Badge variant={error ? "destructive" : "secondary"}>
            {configurationLabel}
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        {!storage ? (
          <p className="text-sm text-muted-foreground">正在读取归档状态…</p>
        ) : (
          <>
            {!storage.configured && (
              <Alert>
                <AlertDescription>
                  尚未配置对象存储。采集继续运行，图片任务会留存；配置完成并重启服务后自动补存。
                </AlertDescription>
              </Alert>
            )}
            {error && (
              <Alert variant="destructive">
                <AlertDescription>管理服务不可达，以下统计可能已过期。</AlertDescription>
              </Alert>
            )}
            {storage.capacity_warning && (
              <Alert variant="destructive">
                <AlertDescription>
                  归档容量达到预警阈值。请检查 R2 用量；系统继续保留原图，不会自动删除。
                </AlertDescription>
              </Alert>
            )}
            <div className="grid grid-cols-5 gap-6 text-sm">
              <div>
                <p className="text-muted-foreground">已归档容量</p>
                <p className="mt-2 text-lg font-semibold">
                  {bytesLabel(storage.size_bytes)}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">独立图片</p>
                <p className="mt-2 text-lg font-semibold">{storage.object_count}</p>
              </div>
              <div>
                <p className="text-muted-foreground">待处理 / 处理中</p>
                <p className="mt-2 text-lg font-semibold">
                  {storage.pending} / {storage.processing}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">成功引用 / 失败</p>
                <p className="mt-2 text-lg font-semibold">
                  {storage.stored} / {storage.failed}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">容量预警线</p>
                <p className="mt-2 text-lg font-semibold">
                  {bytesLabel(storage.warning_bytes)}
                </p>
              </div>
            </div>
            {storage.last_error && (
              <p className="text-sm text-destructive">
                最近归档错误：{storage.last_error}
              </p>
            )}
            <div className="flex items-center justify-between gap-4">
              <p className="text-xs text-muted-foreground">
                仅统计本项目确认存储的原图；账户账单和实际总用量以 Cloudflare
                为准。配置状态不代表连接已验收。
              </p>
              <Button
                variant="outline"
                disabled={
                  busy || Boolean(error) || !storage.configured || !storage.failed
                }
                onClick={retry}
              >
                <RefreshCw className={busy ? "animate-spin" : ""} />
                重试失败图片
              </Button>
            </div>
          </>
        )}
        {notice && (
          <p role="status" className="text-sm">
            {notice}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
