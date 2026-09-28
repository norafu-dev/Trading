/** 原始消息面板：展示采集结果，不将消息解读为可执行交易信号。 */
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { MessageSquare } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import type { Dashboard } from "./types";
import { time } from "./presentation";

/** 展示最近入库的消息原文；附件或 Embed 无正文时使用明确占位说明。 */
export function MessagesPanel({ data }: { data: Dashboard | null }) {
  return (
    <Card>
      <CardHeader className="flex flex-row justify-between">
        <div className="space-y-2">
          <CardTitle>最近消息</CardTitle>
          <CardDescription>最近入库的 20 条原始消息，尚未进行 AI 解析。</CardDescription>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="secondary">原始数据</Badge>
          <Button asChild variant="outline" size="sm">
            <Link href="/messages">打开消息浏览</Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {/* 原文以纯文本渲染，保留换行，避免执行消息中的 HTML。 */}
        {data?.messages.length ? (
          <div className="divide-y">
            {data.messages.map((message) => (
              <article key={message.message_id} className="py-4">
                <div className="flex gap-4 text-xs text-muted-foreground">
                  <code>{message.author_id}</code>
                  <span>#{message.channel_id}</span>
                  <time className="ml-auto">{time(message.created_at, true)}</time>
                </div>
                <p className="mt-3 whitespace-pre-wrap break-words text-sm">
                  {message.content || "［附件或 Embed 消息］"}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 py-8 text-sm text-muted-foreground">
            <MessageSquare className="size-7" />
            <p>等待第一条消息</p>
            <p className="text-xs">来源启用且 Discord 连接成功后，新消息会显示在这里。</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
