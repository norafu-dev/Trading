/** 消息浏览器：左侧 Discord 式分组与单行频道，右侧显示只读聊天记录。 */
"use client";

import Link from "next/link";
import { useState, type DragEvent } from "react";
import {
  ChevronDown,
  ChevronRight,
  GripVertical,
  Hash,
  MessageSquare,
  Pencil,
  Plus,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  createChannelGroup,
  deleteChannelGroup,
  renameChannelGroup,
  saveChannelLayout,
} from "./api";
import { GroupEditor } from "./group-editor";
import { MessageFeed } from "./message-feed";
import type {
  ChannelLayout,
  MessageChannel,
  MessageGroup,
  MessageNavigation,
} from "./types";
import { useNavigation } from "./use-navigation";

type ChannelBucket = { groupId: string | null; channels: MessageChannel[] };

/** 按当前分组顺序生成拖拽使用的频道容器，未分组固定放在最后。 */
function navigationBuckets(navigation: MessageNavigation): ChannelBucket[] {
  return [
    ...navigation.groups.map((group) => ({
      groupId: group.id,
      channels: [...group.channels],
    })),
    { groupId: null, channels: [...navigation.ungrouped] },
  ];
}

/** 把分组和频道容器转换成后端完整布局契约，历史频道不参与写入。 */
function layoutPayload(groups: MessageGroup[], buckets: ChannelBucket[]): ChannelLayout {
  return {
    groups: groups.map((group, position) => ({ group_id: group.id, position })),
    channels: buckets.flatMap((bucket) =>
      bucket.channels.flatMap((channel, position) =>
        channel.source_id
          ? [{ source_id: channel.source_id, group_id: bucket.groupId, position }]
          : [],
      ),
    ),
  };
}

/** 在一组频道容器中移动指定来源，并在目标频道前插入或追加到分组末尾。 */
function moveChannel(
  buckets: ChannelBucket[],
  sourceId: string,
  targetGroupId: string | null,
  targetSourceId?: string,
) {
  let dragged: MessageChannel | undefined;
  const next = buckets.map((bucket) => ({
    ...bucket,
    channels: bucket.channels.filter((channel) => {
      if (channel.source_id === sourceId) {
        dragged = channel;
        return false;
      }
      return true;
    }),
  }));
  if (!dragged) return null;
  const target = next.find((bucket) => bucket.groupId === targetGroupId);
  if (!target) return null;
  const targetIndex = targetSourceId
    ? target.channels.findIndex((channel) => channel.source_id === targetSourceId)
    : -1;
  target.channels.splice(
    targetIndex < 0 ? target.channels.length : targetIndex,
    0,
    dragged,
  );
  return next;
}

/** 单行频道按钮；配置来源支持拖拽，删除来源后的历史入口保持只读。 */
function ChannelRow({
  channel,
  selected,
  onSelect,
  onDrop,
}: {
  channel: MessageChannel;
  selected: boolean;
  onSelect: () => void;
  onDrop: (event: DragEvent, targetSourceId: string) => void;
}) {
  /** 写入专用拖拽类型，避免分组拖拽与频道拖拽互相误判。 */
  function startDrag(event: DragEvent) {
    if (!channel.source_id) return;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("application/x-channel-source", channel.source_id);
  }

  return (
    <Button
      draggable={Boolean(channel.source_id)}
      variant={selected ? "secondary" : "ghost"}
      className="group h-9 w-full justify-start gap-1.5 px-2 text-left font-normal"
      aria-label={`查看频道 ${channel.name}`}
      onClick={onSelect}
      onDragStart={startDrag}
      onDragOver={(event) => channel.source_id && event.preventDefault()}
      onDrop={(event) => channel.source_id && onDrop(event, channel.source_id)}
    >
      {channel.source_id && (
        <GripVertical className="size-3.5 shrink-0 cursor-grab opacity-0 group-hover:opacity-60" />
      )}
      <Hash className="size-5 shrink-0 text-muted-foreground" />
      <span className="truncate text-[15px]">{channel.name}</span>
      {channel.archived && (
        <span className="ml-auto text-[10px] text-muted-foreground">历史</span>
      )}
    </Button>
  );
}

/** 组合分组管理、拖拽排序、频道搜索和当前消息区。 */
export function MessageBrowser() {
  const { data, error, refresh } = useNavigation();
  const [selectedChannelId, setSelectedChannelId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [editor, setEditor] = useState<MessageGroup | "new" | null>(null);
  const [actionError, setActionError] = useState("");
  const [savingLayout, setSavingLayout] = useState(false);
  const allChannels = data
    ? [...data.groups.flatMap((group) => group.channels), ...data.ungrouped]
    : [];
  const channel =
    allChannels.find((item) => item.channel_id === selectedChannelId) ?? allChannels[0];
  const normalizedQuery = query.trim().toLowerCase();

  /** 保存新的频道容器布局，完成后立即刷新服务端导航。 */
  async function persistBuckets(buckets: ChannelBucket[], groups = data?.groups ?? []) {
    if (!data || savingLayout) return;
    setSavingLayout(true);
    setActionError("");
    try {
      await saveChannelLayout(layoutPayload(groups, buckets));
      refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "频道排序保存失败");
      refresh();
    } finally {
      setSavingLayout(false);
    }
  }

  /** 把拖拽频道移到目标频道之前；放到标题上时由标题处理为追加。 */
  function dropChannel(
    event: DragEvent,
    targetGroupId: string | null,
    targetSourceId?: string,
  ) {
    event.preventDefault();
    if (!data) return;
    const sourceId = event.dataTransfer.getData("application/x-channel-source");
    if (!sourceId) return;
    const buckets = moveChannel(
      navigationBuckets(data),
      sourceId,
      targetGroupId,
      targetSourceId,
    );
    if (buckets) void persistBuckets(buckets);
  }

  /** 拖动分组标题调整分组顺序，频道内部顺序保持不变。 */
  function dropGroup(event: DragEvent, targetGroupId: string) {
    event.preventDefault();
    if (!data) return;
    const draggedId = event.dataTransfer.getData("application/x-channel-group");
    if (!draggedId || draggedId === targetGroupId) return;
    const groups = [...data.groups];
    const from = groups.findIndex((group) => group.id === draggedId);
    const to = groups.findIndex((group) => group.id === targetGroupId);
    if (from < 0 || to < 0) return;
    const [dragged] = groups.splice(from, 1);
    groups.splice(to, 0, dragged);
    void persistBuckets(navigationBuckets(data), groups);
  }

  /** 展开或折叠分组，只改变本地阅读状态。 */
  function toggleGroup(groupId: string) {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }

  /** 创建或重命名当前弹窗中的分组。 */
  async function saveGroup(name: string) {
    if (editor === "new") await createChannelGroup(name);
    else if (editor) await renameChannelGroup(editor.id, name);
    setEditor(null);
    refresh();
  }

  /** 删除当前编辑分组，所属频道会回到未分组。 */
  async function removeGroup() {
    if (!editor || editor === "new") return;
    await deleteChannelGroup(editor.id);
    setEditor(null);
    refresh();
  }

  /** 渲染一个分组标题和其单行频道列表。 */
  function renderGroup(group: MessageGroup) {
    const isCollapsed = collapsed.has(group.id);
    const channels = group.channels.filter((item) =>
      `${group.name} ${item.name} ${item.channel_id}`
        .toLowerCase()
        .includes(normalizedQuery),
    );
    if (normalizedQuery && !channels.length) return null;
    return (
      <section key={group.id} className="mb-3" aria-label={`${group.name} 分组`}>
        <div
          draggable
          className="group flex h-8 items-center gap-1 px-2 text-xs font-semibold tracking-wide text-muted-foreground"
          onDragStart={(event) => {
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("application/x-channel-group", group.id);
          }}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            if (event.dataTransfer.getData("application/x-channel-source"))
              dropChannel(event, group.id);
            else dropGroup(event, group.id);
          }}
        >
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={`${isCollapsed ? "展开" : "折叠"} ${group.name}`}
            onClick={() => toggleGroup(group.id)}
          >
            {isCollapsed ? <ChevronRight /> : <ChevronDown />}
          </Button>
          <span className="min-w-0 flex-1 truncate uppercase">{group.name}</span>
          <Button
            variant="ghost"
            size="icon-xs"
            className="opacity-0 group-hover:opacity-100"
            aria-label={`编辑分组 ${group.name}`}
            onClick={() => setEditor(group)}
          >
            <Pencil />
          </Button>
        </div>
        {!isCollapsed && (
          <div className="space-y-0.5">
            {channels.map((item) => (
              <ChannelRow
                key={item.channel_id}
                channel={item}
                selected={item.channel_id === channel?.channel_id}
                onSelect={() => setSelectedChannelId(item.channel_id)}
                onDrop={(event, target) => dropChannel(event, group.id, target)}
              />
            ))}
            {!channels.length && (
              <p className="px-8 py-2 text-xs text-muted-foreground">
                拖动频道到这个分组
              </p>
            )}
          </div>
        )}
      </section>
    );
  }

  const visibleUngrouped =
    data?.ungrouped.filter((item) =>
      `${item.name} ${item.channel_id}`.toLowerCase().includes(normalizedQuery),
    ) ?? [];

  return (
    <div className="flex h-screen min-w-0 flex-1 flex-col">
      {(error || actionError) && (
        <Alert variant="destructive" className="rounded-none">
          <AlertDescription>
            {actionError || `导航读取失败：${error}。正在自动重试。`}
          </AlertDescription>
        </Alert>
      )}
      <div className="flex min-h-0 flex-1">
        <aside
          aria-label="频道列表"
          className="flex w-80 shrink-0 flex-col border-r bg-muted/35"
        >
          <header className="flex h-20 shrink-0 items-center justify-between border-b px-4">
            <div>
              <h2 className="font-semibold">采集频道</h2>
              <p className="mt-1 text-xs text-muted-foreground">拖拽频道即可分组与排序</p>
            </div>
            <Button
              size="icon-sm"
              variant="outline"
              aria-label="新建频道分组"
              onClick={() => setEditor("new")}
            >
              <Plus />
            </Button>
          </header>
          <div className="p-3">
            <Input
              aria-label="搜索频道"
              placeholder="搜索频道名称或 ID"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <div
            className="min-h-0 flex-1 overflow-y-auto px-2 pb-5"
            aria-busy={savingLayout}
          >
            {data?.groups.map(renderGroup)}
            <section
              aria-label="未分组频道"
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => dropChannel(event, null)}
            >
              <div className="flex h-8 items-center px-3 text-xs font-semibold tracking-wide text-muted-foreground">
                未分组
              </div>
              <div className="space-y-0.5">
                {visibleUngrouped.map((item) => (
                  <ChannelRow
                    key={item.channel_id}
                    channel={item}
                    selected={item.channel_id === channel?.channel_id}
                    onSelect={() => setSelectedChannelId(item.channel_id)}
                    onDrop={(event, target) => dropChannel(event, null, target)}
                  />
                ))}
              </div>
            </section>
          </div>
        </aside>
        {channel ? (
          <MessageFeed key={channel.channel_id} channel={channel} />
        ) : (
          <section className="flex flex-1 flex-col items-center justify-center gap-4 bg-card text-muted-foreground">
            <MessageSquare className="size-12" />
            <h1 className="text-lg font-medium text-foreground">
              {data ? "还没有可浏览的频道" : "正在加载消息工作区"}
            </h1>
            {data && (
              <Button asChild>
                <Link href="/#sources">配置采集来源</Link>
              </Button>
            )}
          </section>
        )}
      </div>
      {editor && (
        <GroupEditor
          group={editor === "new" ? null : editor}
          onClose={() => setEditor(null)}
          onSave={saveGroup}
          onDelete={editor === "new" ? null : removeGroup}
        />
      )}
    </div>
  );
}
