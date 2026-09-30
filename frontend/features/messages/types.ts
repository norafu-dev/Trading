/** 消息浏览器的数据契约，对应后端频道分组导航和分页接口。 */
export type MessageChannel = {
  channel_id: string;
  source_id: string | null;
  group_id: string | null;
  position: number;
  name: string;
  enabled: boolean;
  archived: boolean;
  message_count: number;
};
export type MessageGroup = {
  id: string;
  name: string;
  position: number;
  channels: MessageChannel[];
};
export type MessageNavigation = {
  groups: MessageGroup[];
  ungrouped: MessageChannel[];
};
export type CollectedMessage = {
  message_id: string;
  channel_id: string;
  author_id: string;
  content: string;
  created_at: string;
  first_seen_at: string;
  first_delivery: "unknown" | "realtime" | "backfill";
  collection_delay_seconds: number;
  edited_at: string | null;
  deleted_at: string | null;
  is_stale: boolean;
  freshness_seconds: number;
  author_name: string | null;
  reply_to_message_id: string | null;
  attachments: Array<{
    filename: string;
    url: string;
    content_type: string | null;
    archive_status: string | null;
    archive_error: string | null;
  }>;
  embeds: Array<{
    title: string | null;
    description: string | null;
    url: string | null;
    image_url: string | null;
    archive_status: string | null;
    archive_error: string | null;
    fields: Array<{ name: string; value: string; inline: boolean }>;
    footer: string | null;
    timestamp: string | null;
    color: string | null;
  }>;
};
export type MessagePage = { messages: CollectedMessage[]; next_before: string | null };
export type ChannelLayout = {
  groups: Array<{ group_id: string; position: number }>;
  channels: Array<{ source_id: string; group_id: string | null; position: number }>;
};
