/** 采集概览指标；四张 shadcn Card 共享卡片样式，不实现独立基础控件。 */
import type { ReactNode } from "react";
import { Hash, MessageSquare, ArrowDownToLine, Activity } from "lucide-react";
import { Card, CardHeader, CardDescription, CardContent } from "@/components/ui/card";
import type { Dashboard } from "./types";
import { time } from "./presentation";

/** 从最近一次响应呈现计数和状态；未加载时显示占位，避免把未知数据当作零。 */
export function Overview({
  data,
  status,
}: {
  data: Dashboard | null;
  status: { label: string; tone: string };
}) {
  return (
    <section className="grid grid-cols-4 gap-5" aria-label="采集概览">
      <Metric
        label="已启用来源"
        value={
          data
            ? String(data.sources.filter((source) => source.enabled).length).padStart(
                2,
                "0",
              )
            : "—"
        }
        hint={data ? `共 ${data.sources.length} 个采集来源` : "正在读取配置"}
        icon={<Hash className="size-4" />}
      />
      <Metric
        label="累计采集消息"
        value={data ? data.total_messages.toLocaleString() : "—"}
        hint="去重后已保存的消息"
        icon={<MessageSquare className="size-4" />}
      />
      <Metric
        label="最近消息入库"
        value={time(data?.runtime.last_saved_at)}
        hint={
          data?.runtime.last_saved_at ? "本地时间 · 成功写入 PostgreSQL" : "暂未收到消息"
        }
        icon={<ArrowDownToLine className="size-4" />}
        compact
      />
      <Metric
        label="Collector 状态"
        value={data ? status.label : "读取中"}
        hint={
          data
            ? `${data.runtime.process_alive ? "进程在线" : "进程未确认在线"} · ${data.runtime.active_sources} 个已加载来源`
            : "等待服务响应"
        }
        icon={<Activity className="size-4" />}
        compact
      />
    </section>
  );
}

/** 组合单个业务指标的标题、值和说明，沿用 Card 的边框、间距与语义颜色。 */
function Metric({
  label,
  value,
  hint,
  icon,
  compact = false,
}: {
  label: string;
  value: string;
  hint: string;
  icon: ReactNode;
  compact?: boolean;
}) {
  return (
    <Card className="gap-4">
      <CardHeader>
        <CardDescription className="flex items-center justify-between">
          {label}
          {icon}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p
          className={
            compact ? "text-xl font-semibold" : "text-3xl font-semibold tabular-nums"
          }
        >
          {value}
        </p>
        <p className="mt-3 text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}
