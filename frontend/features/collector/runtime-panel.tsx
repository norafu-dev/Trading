/** 运行状态展示：区分 Discord 会话、Collector 心跳与数据库响应。 */
import { Radio, Activity, Database, CircleHelp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { Dashboard } from "./types";
import { time } from "./presentation";

/** API 读取失败时将在线状态标为未知，同时保留最后读取的时间供排查。 */
export function RuntimePanel({ data, error }: { data: Dashboard | null; error: string }) {
  const isAlive = Boolean(data?.runtime.process_alive && !error);
  const isConnected = data?.runtime.state === "connected" && !error;
  return (
    <Card>
      <CardHeader className="flex flex-row justify-between">
        <div className="space-y-2">
          <CardTitle>运行状态</CardTitle>
          <CardDescription>进程心跳与 Discord 会话分别监控。</CardDescription>
        </div>
        <Badge variant={isAlive ? "success" : "secondary"}>
          {isAlive ? "在线" : "未确认在线"}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid grid-cols-3 gap-3 rounded-lg bg-muted/50 p-5 text-center text-sm">
          <div className="space-y-2">
            <Radio className="mx-auto size-5 text-primary" />
            <p className="font-medium">Discord</p>
            <p className="text-xs text-muted-foreground">
              {isConnected ? "已连接" : "未确认连接"}
            </p>
          </div>
          <div className="space-y-2">
            <Activity className="mx-auto size-5 text-primary" />
            <p className="font-medium">Collector</p>
            <p className="text-xs text-muted-foreground">
              {isAlive ? "心跳正常" : "等待心跳"}
            </p>
          </div>
          <div className="space-y-2">
            <Database className="mx-auto size-5 text-primary" />
            <p className="font-medium">PostgreSQL</p>
            <p className="text-xs text-muted-foreground">
              {data && !error ? "可访问" : "等待响应"}
            </p>
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="mb-1 text-xs text-muted-foreground">最近心跳</dt>
            <dd>{time(data?.runtime.heartbeat_at, true)}</dd>
          </div>
          <div>
            <dt className="mb-1 text-xs text-muted-foreground">进程启动</dt>
            <dd>{time(data?.runtime.started_at, true)}</dd>
          </div>
          <div>
            <dt className="mb-1 text-xs text-muted-foreground">配置同步</dt>
            <dd>{time(data?.runtime.source_sync_at, true)}</dd>
          </div>
          <div>
            <dt className="mb-1 text-xs text-muted-foreground">当前加载来源</dt>
            <dd>{data?.runtime.active_sources ?? "—"}</dd>
          </div>
        </dl>
        {data?.runtime.last_error && (
          <Alert variant="destructive">
            <AlertDescription>{data.runtime.last_error}</AlertDescription>
          </Alert>
        )}
      </CardContent>
      <CardFooter className="gap-2 border-t pt-4 text-xs text-muted-foreground">
        <CircleHelp className="size-4" />
        当前阶段仅实时采集，断线消息补采尚未实现。
      </CardFooter>
    </Card>
  );
}
