/** Collector 和配置审计事件列表；不向浏览器展示原始服务日志。 */
import { Activity } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import type { Dashboard } from "./types";
import { time, eventTone, badgeVariant } from "./presentation";

/** 展示服务器返回的最近事件，事件级别通过统一 Badge 变体表达。 */
export function EventsPanel({ data, error }: { data: Dashboard | null; error: string }) {
  return (
    <Card id="activity" className="scroll-mt-6">
      <CardHeader className="flex flex-row justify-between">
        <div className="space-y-2">
          <CardTitle>运行动态</CardTitle>
          <CardDescription>最近 20 条服务与配置事件</CardDescription>
        </div>
        <Badge variant={error ? "destructive" : "outline"}>
          {error ? "更新中断" : "每 5 秒更新"}
        </Badge>
      </CardHeader>
      <CardContent className="max-h-72 overflow-y-auto">
        {/* API 已按最新事件排序，这里保留顺序并格式化本地时间。 */}
        {data?.events.length ? (
          <div className="space-y-4">
            {data.events.map((event) => (
              <div key={event.id} className="flex items-start gap-3">
                <Badge variant={badgeVariant(eventTone(event.level))} className="mt-0.5">
                  <Activity className="size-3" />
                </Badge>
                <div>
                  <p className="text-sm">{event.message}</p>
                  <time className="text-xs text-muted-foreground">
                    {time(event.occurred_at, true)}
                  </time>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="py-12 text-center text-sm text-muted-foreground">
            还没有运行事件，服务启动和来源变更会记录在这里。
          </p>
        )}
      </CardContent>
    </Card>
  );
}
