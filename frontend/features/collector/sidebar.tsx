/** PC 工作台的静态导航；使用 shadcn Button 链接变体复用交互样式。 */
import Link from "next/link";
import {
  Activity,
  Radio,
  Hash,
  Layers3,
  ArrowUpRight,
  ShieldCheck,
  MessageSquare,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

/** 展示当前采集阶段和页面锚点，不为尚未实现的功能创建可点击入口。 */
export function Sidebar({ active = "collector" }: { active?: "collector" | "messages" }) {
  return (
    <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r bg-card px-5 py-7">
      <Link
        href="/#overview"
        className="flex items-center gap-3 px-2 text-xl font-semibold"
      >
        <span className="rounded-lg bg-primary p-2 text-primary-foreground">
          <Activity className="size-5" />
        </span>
        signal<span className="-ml-3 font-normal text-muted-foreground">desk</span>
      </Link>
      <div className="my-8 flex items-center gap-3 rounded-lg bg-muted p-3">
        <span className="flex size-9 items-center justify-center rounded-md bg-card font-semibold">
          N
        </span>
        <div className="text-sm font-medium">
          个人工作空间
          <p className="text-xs font-normal text-muted-foreground">Local workspace</p>
        </div>
        <Badge variant="outline">M1</Badge>
      </div>
      <p className="mb-3 px-3 text-xs text-muted-foreground">工作台</p>
      <nav aria-label="主导航" className="space-y-2">
        <Button
          asChild
          variant={active === "collector" ? "secondary" : "ghost"}
          className="w-full justify-start"
        >
          <Link href="/#overview">
            <Radio />
            消息采集
          </Link>
        </Button>
        <Button asChild variant="ghost" className="w-full justify-start">
          <Link href="/#sources">
            <Hash />
            采集来源
          </Link>
        </Button>
        <Button asChild variant="ghost" className="w-full justify-start">
          <Link href="/#activity">
            <Activity />
            运行动态
          </Link>
        </Button>
        <Button
          asChild
          variant={active === "messages" ? "secondary" : "ghost"}
          className="w-full justify-start"
        >
          <Link href="/messages">
            <MessageSquare />
            消息浏览
          </Link>
        </Button>
      </nav>
      <Separator className="my-6" />
      <p className="mb-3 px-3 text-xs text-muted-foreground">后续阶段</p>
      <div className="space-y-4 px-3 text-sm text-muted-foreground">
        <div className="flex items-center gap-2">
          <Layers3 className="size-4" />
          信号解析
          <Badge variant="outline" className="ml-auto">
            待开发
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <ArrowUpRight className="size-4" />
          交易执行
          <Badge variant="outline" className="ml-auto">
            待开发
          </Badge>
        </div>
      </div>
      <div className="mt-auto space-y-3 px-3 text-xs text-muted-foreground">
        <p className="flex items-center gap-2">
          <ShieldCheck className="size-4" />
          本机运行环境
        </p>
        <p>先记录消息，再理解信号。</p>
        <Separator />
        <p>Docker workspace · v0.1</p>
      </div>
    </aside>
  );
}
