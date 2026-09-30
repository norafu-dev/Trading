/** 与 FastAPI 响应模型对应的面板类型，以及来源表单和编辑模式契约。 */
export type Source = {
  id: string;
  name: string;
  kol_name: string;
  group_id: string | null;
  position: number;
  channel_id: string;
  author_ids: string[];
  enabled: boolean;
  status: string;
  last_error: string | null;
  checked_at: string | null;
};
export type Runtime = {
  state: string;
  process_alive: boolean;
  heartbeat_at: string | null;
  heartbeat_age_seconds: number | null;
  started_at: string | null;
  connected_at: string | null;
  last_message_at: string | null;
  last_saved_at: string | null;
  source_sync_at: string | null;
  active_sources: number;
  last_error: string | null;
};
export type Message = {
  message_id: string;
  channel_id: string;
  author_id: string;
  content: string;
  created_at: string;
};
export type Event = {
  id: string;
  level: string;
  message: string;
  occurred_at: string;
};
export type StorageSummary = {
  configured: boolean;
  object_count: number;
  size_bytes: number;
  warning_bytes: number;
  capacity_warning: boolean;
  pending: number;
  processing: number;
  stored: number;
  failed: number;
  last_error: string | null;
};
export type Dashboard = {
  storage: StorageSummary;
  sources: Source[];
  runtime: Runtime;
  total_messages: number;
  messages: Message[];
  events: Event[];
  server_time: string;
};
export type SourceBody = Pick<
  Source,
  "name" | "kol_name" | "group_id" | "position" | "channel_id" | "author_ids" | "enabled"
>;

export type EditorState = { mode: "create" } | { mode: "edit"; source: Source };
