/** Discord 风格的只读聊天区；分页读取留存消息，不提供发送或交易操作。 */
import { Fragment, useLayoutEffect, useRef } from "react";
import Image from "next/image";
import {
  Hash,
  ArrowDown,
  LoaderCircle,
  MessageSquare,
  Paperclip,
  CornerDownRight,
  FileText,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useMessageFeed } from "./use-message-feed";
import type { MessageChannel } from "./types";

/** 将 UTC 时间转换为本地完整日期，作为消息组的日期分隔标题。 */
function dayLabel(value: string) {
  return new Date(value).toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

/** 判断附件是否可直接作为图片展示；Discord 未提供类型时按常见扩展名补充判断。 */
function isImageAttachment(filename: string, contentType: string | null) {
  return Boolean(
    contentType?.startsWith("image/") || /\.(?:png|jpe?g|webp|gif)$/i.test(filename),
  );
}

/** 展示选定作者与频道的聊天记录，新消息仅在用户停留底部时自动跟随。 */
export function MessageFeed({ channel }: { channel: MessageChannel }) {
  const { page, error, loadingOlder, loadOlder } = useMessageFeed(channel.channel_id);
  const viewport = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const olderHeight = useRef<number | null>(null);

  // 历史消息插入顶部后补偿滚动高度；正常刷新只在用户未向上阅读时跟随底部。
  useLayoutEffect(() => {
    const element = viewport.current;
    if (!element) return;
    if (olderHeight.current !== null) {
      element.scrollTop += element.scrollHeight - olderHeight.current;
      olderHeight.current = null;
    } else if (followLatest.current) element.scrollTop = element.scrollHeight;
  }, [page?.messages]);

  /** 记录用户是否正在查看最新消息，不因后台轮询打断历史阅读位置。 */
  function trackScroll() {
    const element = viewport.current;
    if (element)
      followLatest.current =
        element.scrollHeight - element.scrollTop - element.clientHeight < 80;
  }

  /** 保存翻页前的高度，使更早的消息加载后原有内容保持在视口中。 */
  async function showOlder() {
    olderHeight.current = viewport.current?.scrollHeight ?? null;
    await loadOlder();
  }

  /** 主动滚动到最新消息并重新开启自动跟随。 */
  function scrollToLatest() {
    followLatest.current = true;
    viewport.current?.scrollTo({
      top: viewport.current.scrollHeight,
      behavior: "smooth",
    });
  }

  return (
    <section aria-label="频道消息" className="flex min-w-0 flex-1 flex-col bg-card">
      <header className="flex h-20 shrink-0 items-center gap-3 border-b px-6">
        <Hash className="size-6 text-muted-foreground" />
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold">{channel.name}</h1>
          <p className="truncate text-xs text-muted-foreground">{channel.channel_id}</p>
        </div>
        <Badge variant="secondary" className="ml-auto">
          只读采集
        </Badge>
      </header>
      {error && (
        <Alert variant="destructive" className="m-4 w-auto">
          <AlertDescription>{error}。已有记录保留，正在自动重试。</AlertDescription>
        </Alert>
      )}
      <div
        ref={viewport}
        onScroll={trackScroll}
        className="min-h-0 flex-1 overflow-y-auto px-6 py-5"
        aria-label="已采集消息列表"
        aria-busy={!page && !error}
      >
        {!page && !error && (
          <div className="flex items-center justify-center gap-2 py-20 text-muted-foreground">
            <LoaderCircle className="size-5 animate-spin" />
            正在读取消息…
          </div>
        )}
        {page?.next_before && (
          <div className="mb-6 text-center">
            <Button
              variant="outline"
              size="sm"
              disabled={loadingOlder}
              onClick={showOlder}
            >
              {loadingOlder ? "正在读取…" : "加载更早消息"}
            </Button>
          </div>
        )}
        {page && !page.messages.length && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-muted-foreground">
            <MessageSquare className="size-10" />
            <h2 className="font-medium text-foreground">这个频道还没有采集消息</h2>
            <p className="text-sm">连接 Discord 并启用来源后，新消息会显示在这里。</p>
          </div>
        )}
        {/* 时间分隔按本地日期呈现；原文使用纯文本，保留换行但不执行 HTML。 */}
        {page?.messages.map((message, index) => {
          const newDay =
            index === 0 ||
            dayLabel(page.messages[index - 1].created_at) !==
              dayLabel(message.created_at);
          const authorName = message.author_name || message.author_id;
          return (
            <Fragment key={message.message_id}>
              {newDay && (
                <div className="my-6 flex items-center gap-3">
                  <div className="h-px flex-1 bg-border" />
                  <span className="text-xs text-muted-foreground">
                    {dayLabel(message.created_at)}
                  </span>
                  <div className="h-px flex-1 bg-border" />
                </div>
              )}
              <article
                className="group -mx-3 flex gap-3 rounded-md px-3 py-3 hover:bg-muted/50"
                aria-label={`来自 ${authorName} 的消息`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-3">
                    <span className="font-semibold">{authorName}</span>
                    <time
                      dateTime={message.created_at}
                      title={new Date(message.created_at).toLocaleString("zh-CN")}
                      className="text-xs text-muted-foreground"
                    >
                      {new Date(message.created_at).toLocaleTimeString("zh-CN", {
                        hour: "2-digit",
                        minute: "2-digit",
                        hour12: false,
                      })}
                    </time>
                  </div>
                  {message.reply_to_message_id && (
                    <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                      <CornerDownRight className="size-3" />
                      回复消息 {message.reply_to_message_id}
                    </p>
                  )}
                  {message.content && (
                    <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-7">
                      {message.content}
                    </p>
                  )}
                  {message.attachments.map((attachment) =>
                    isImageAttachment(attachment.filename, attachment.content_type) ? (
                      <a
                        key={attachment.url}
                        href={attachment.url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-3 block w-fit overflow-hidden rounded-lg border bg-muted"
                      >
                        <Image
                          src={attachment.url}
                          alt={attachment.filename}
                          width={720}
                          height={480}
                          unoptimized
                          className="max-h-[520px] w-auto max-w-[720px] object-contain"
                        />
                      </a>
                    ) : (
                      <a
                        key={attachment.url}
                        href={attachment.url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-3 flex w-fit items-center gap-2 rounded-md border px-3 py-2 text-sm text-primary hover:bg-muted"
                      >
                        <Paperclip className="size-4" />
                        {attachment.filename}
                      </a>
                    ),
                  )}
                  {message.embeds.map((embed, embedIndex) => (
                    <div
                      key={`${message.message_id}-embed-${embedIndex}`}
                      className="mt-3 max-w-[720px] overflow-hidden rounded-md border-l-4 border-primary bg-muted/70"
                      style={embed.color ? { borderLeftColor: embed.color } : undefined}
                    >
                      {(embed.title || embed.description || embed.fields.length > 0) && (
                        <div className="space-y-1 px-4 py-3">
                          {embed.title && <p className="font-semibold">{embed.title}</p>}
                          {embed.description && (
                            <p className="whitespace-pre-wrap break-words text-sm leading-6">
                              {embed.description}
                            </p>
                          )}
                          {embed.fields.length > 0 && (
                            <div className="grid grid-cols-3 gap-3 pt-2">
                              {embed.fields.map((field, fieldIndex) => (
                                <div
                                  key={`${message.message_id}-embed-${embedIndex}-field-${fieldIndex}`}
                                  className={field.inline ? "col-span-1" : "col-span-3"}
                                >
                                  <p className="text-sm font-semibold">{field.name}</p>
                                  <p className="whitespace-pre-wrap break-words text-sm">
                                    {field.value}
                                  </p>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                      {embed.image_url && (
                        <Image
                          src={embed.image_url}
                          alt={embed.title || "Discord Embed 图片"}
                          width={720}
                          height={480}
                          unoptimized
                          className="max-h-[520px] w-auto max-w-full object-contain"
                        />
                      )}
                      {(embed.footer || embed.timestamp) && (
                        <p className="px-4 py-2 text-xs text-muted-foreground">
                          {[
                            embed.footer,
                            embed.timestamp
                              ? new Date(embed.timestamp).toLocaleString("zh-CN")
                              : null,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </p>
                      )}
                    </div>
                  ))}
                  {!message.content &&
                    !message.attachments.length &&
                    !message.embeds.length && (
                      <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                        <FileText className="size-3" />
                        这条消息没有可显示的正文或媒体
                      </p>
                    )}
                </div>
              </article>
            </Fragment>
          );
        })}
      </div>
      <footer className="flex h-14 shrink-0 items-center justify-between border-t bg-muted/20 px-6 text-xs text-muted-foreground">
        <span>已显示 {page?.messages.length ?? 0} 条 · 每 5 秒读取已采集消息</span>
        <Button variant="ghost" size="sm" onClick={scrollToLatest}>
          <ArrowDown />
          回到最新
        </Button>
      </footer>
    </section>
  );
}
