/** 来源管理列表：组合 shadcn 表格、搜索输入、状态标签、开关和操作按钮。 */
import { Hash, Pencil, Trash2, RefreshCw, Plus, ShieldCheck, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableHead,
  TableRow,
  TableBody,
  TableCell,
} from "@/components/ui/table";
import type { Dashboard, Source } from "./types";
import { sourceStatus, badgeVariant } from "./presentation";

/** 按名称或 ID 筛选来源；变更通过父组件处理，使该组件只负责列表交互和展示。 */
export function SourcesPanel({
  data,
  query,
  setQuery,
  busy,
  onEdit,
  onCreate,
  toggle,
  remove,
}: {
  data: Dashboard | null;
  query: string;
  setQuery: (value: string) => void;
  busy: string | null;
  onEdit: (source: Source) => void;
  onCreate: () => void;
  toggle: (source: Source) => Promise<void>;
  remove: (source: Source) => void;
}) {
  // 同时检索名称、频道和作者；不改变服务端保存的原始配置。
  const filtered =
    data?.sources.filter((source) =>
      `${source.name} ${source.kol_name} ${source.channel_id} ${source.author_ids.join(" ")}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    ) ?? [];
  return (
    <Card id="sources" className="scroll-mt-6">
      <CardHeader className="flex flex-row items-center justify-between">
        <div className="space-y-2">
          <CardTitle className="flex items-center gap-2">
            采集来源<Badge variant="secondary">{data?.sources.length ?? "—"}</Badge>
          </CardTitle>
          <CardDescription>指定频道或 Thread，只保留所选 Trader 的消息。</CardDescription>
        </div>
        <div className="relative w-72">
          <Search className="absolute top-2.5 left-3 size-4 text-muted-foreground" />
          <Input
            className="pl-9"
            aria-label="搜索采集来源"
            placeholder="搜索名称、频道或作者 ID"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      </CardHeader>
      <CardContent className="px-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">KOL</TableHead>
              <TableHead>频道名称</TableHead>
              <TableHead>频道 / THREAD ID</TableHead>
              <TableHead>TRADER 作者</TableHead>
              <TableHead>配置状态</TableHead>
              <TableHead>启用</TableHead>
              <TableHead className="pr-6 text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {/* 每行绑定自身来源；busy 防止同一来源重复提交变更。 */}
            {filtered.map((source) => (
              <TableRow key={source.id}>
                <TableCell className="max-w-60 py-5 pl-6">
                  <div className="flex items-center gap-3">
                    <span className="rounded-lg bg-muted p-2 text-muted-foreground">
                      <Hash className="size-4" />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate font-medium" title={source.kol_name}>
                        {source.kol_name}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">自定义展示资料</p>
                    </div>
                  </div>
                </TableCell>
                <TableCell className="max-w-48 truncate" title={source.name}>
                  <span className="inline-flex items-center gap-2">
                    <Hash className="size-4" />
                    {source.name}
                  </span>
                </TableCell>
                <TableCell className="font-mono text-xs">{source.channel_id}</TableCell>
                <TableCell>
                  <div className="flex max-h-24 flex-col gap-1 overflow-y-auto font-mono text-xs">
                    {source.author_ids.map((id) => (
                      <span key={id}>{id}</span>
                    ))}
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant={badgeVariant(sourceStatus(source).tone)}>
                    {sourceStatus(source).label}
                  </Badge>
                  {source.enabled && source.last_error && (
                    <p className="mt-1 max-w-52 whitespace-normal text-xs text-destructive">
                      {source.last_error}
                    </p>
                  )}
                </TableCell>
                <TableCell>
                  <Switch
                    aria-label={`${source.enabled ? "停用" : "启用"} ${source.name}`}
                    checked={source.enabled}
                    disabled={busy === source.id}
                    onCheckedChange={() => void toggle(source)}
                  />
                </TableCell>
                <TableCell className="pr-6">
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`编辑 ${source.name}`}
                      onClick={() => onEdit(source)}
                      disabled={busy === source.id}
                    >
                      <Pencil />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-destructive"
                      aria-label={`移除 ${source.name}`}
                      onClick={() => void remove(source)}
                      disabled={busy === source.id}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {!data && (
          <div className="flex flex-col items-center gap-3 py-12 text-muted-foreground">
            <RefreshCw className="size-6 animate-spin" />
            <p>正在载入采集配置</p>
          </div>
        )}
        {data && !filtered.length && (
          <div className="flex flex-col items-center gap-3 py-12">
            <Hash className="size-7 text-muted-foreground" />
            <h3 className="font-medium">
              {query ? "没有匹配的来源" : "从第一个 Trader 开始"}
            </h3>
            <p className="text-sm text-muted-foreground">
              {query
                ? "试试其他名称或 ID。"
                : "添加频道或 Thread，并填写 Trader 作者 ID。"}
            </p>
            {!query && (
              <Button variant="outline" onClick={onCreate}>
                <Plus />
                添加第一个来源
              </Button>
            )}
          </div>
        )}
      </CardContent>
      <CardFooter className="gap-2 border-t pt-4 text-xs text-muted-foreground">
        <ShieldCheck className="size-4" />
        <span>配置保存在数据库中 · 通常约 5 秒同步 · 停用或移除不会删除历史消息</span>
        <span className="ml-auto">{data ? `${filtered.length} 个来源` : "—"}</span>
      </CardFooter>
    </Card>
  );
}
