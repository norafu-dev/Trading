/** 消息浏览器只读请求，复用面板同源请求的超时与错误处理。 */
import { request } from "@/features/collector/api";
import type { ChannelLayout, MessageNavigation, MessagePage } from "./types";

/** 读取配置及历史消息合并后的 KOL 导航；调用方负责取消过期请求。 */
export async function readNavigation(signal: AbortSignal): Promise<MessageNavigation> {
  const response = await request("messages/navigation", "GET", undefined, signal);
  return response.json();
}

/** 按频道和可选历史游标读取一页消息，ID 全程保持字符串。 */
export async function readMessages(
  channelId: string,
  signal: AbortSignal,
  before?: string,
): Promise<MessagePage> {
  const params = new URLSearchParams({ channel_id: channelId });
  if (before) params.set("before", before);
  const response = await request(`messages?${params}`, "GET", undefined, signal);
  return response.json();
}

/** 新增频道分组；位置由服务端追加到末尾。 */
export async function createChannelGroup(name: string): Promise<void> {
  await request("channel-groups", "POST", { name });
}

/** 修改已有频道分组名称。 */
export async function renameChannelGroup(groupId: string, name: string): Promise<void> {
  await request(`channel-groups/${groupId}`, "PUT", { name });
}

/** 删除频道分组，其中的频道由数据库外键移回未分组。 */
export async function deleteChannelGroup(groupId: string): Promise<void> {
  await request(`channel-groups/${groupId}`, "DELETE");
}

/** 原子保存拖拽后的完整分组和频道顺序。 */
export async function saveChannelLayout(layout: ChannelLayout): Promise<void> {
  await request("channel-layout", "PUT", layout);
}
