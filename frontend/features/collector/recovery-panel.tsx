/** 展示各频道独立补采状态，区分当前检查完成、排队和失败重试。 */
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Dashboard } from "./types";

/** 将补采记录时间转换为本地时间，缺少完成记录时明确表示尚未完成。 */
function recoveryTime(value: string | null) {
  return value ? new Date(value).toLocaleString("zh-CN") : "尚未完成";
}

/** 只呈现数据库已记录的覆盖范围，不能以 Discord 已连接代替缺口补齐。 */
export function RecoveryPanel({
  data,
  error,
}: {
  data: Dashboard | null;
  error: string;
}) {
  const states: Record<string, string> = {
    pending: "等待继续",
    running: "检查中",
    error: "等待重试",
    idle: "本轮已完成",
  };
  return (
    <Card id="recovery">
      <CardHeader>
        <CardTitle>消息补采</CardTitle>
        <CardDescription>
          {error
            ? "管理服务不可达，以下补采记录可能已过期，暂时无法确认当前状态。"
            : "按独立断点持续检查。覆盖起点之前的历史，以及断线期间已删除的消息，不保证完整。"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>频道</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>覆盖起点</TableHead>
              <TableHead>最近完成检查</TableHead>
              <TableHead>重试情况</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.checkpoints.map((checkpoint) => (
              <TableRow key={checkpoint.channel_id}>
                <TableCell>{checkpoint.name}</TableCell>
                <TableCell>
                  <Badge
                    variant={checkpoint.state === "error" ? "destructive" : "secondary"}
                  >
                    {error ? "状态待确认" : states[checkpoint.state] || checkpoint.state}
                  </Badge>
                </TableCell>
                <TableCell>{recoveryTime(checkpoint.coverage_started_at)}</TableCell>
                <TableCell>{recoveryTime(checkpoint.last_completed_at)}</TableCell>
                <TableCell>
                  {checkpoint.last_error ? (
                    <>
                      <p>{checkpoint.last_error}</p>
                      <p className="text-xs text-muted-foreground">
                        连续失败 {checkpoint.attempts} 次 · 下次{" "}
                        {recoveryTime(checkpoint.next_attempt_at)}
                      </p>
                    </>
                  ) : (
                    "无待处理错误"
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {!data?.checkpoints.length && (
          <p className="py-4 text-sm text-muted-foreground">
            来源验证完成后建立补采进度。
          </p>
        )}
      </CardContent>
    </Card>
  );
}
