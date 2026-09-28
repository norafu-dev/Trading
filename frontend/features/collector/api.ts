/** 面板同源 HTTP 客户端；集中处理超时、取消和脱敏错误响应。 */
import type { Dashboard, SourceBody } from "./types";
/** 发送同源面板请求并限制超时；失败时缩窄未知响应，只暴露可展示的错误。 */
export async function request(
  path: string,
  method = "GET",
  body?: object,
  signal?: AbortSignal,
) {
  const response = await fetch(`/api/${path}`, {
    method,
    cache: "no-store",
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(10000)])
      : AbortSignal.timeout(10000),
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "trading-panel",
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null);
    throw new Error(
      data !== null &&
      typeof data === "object" &&
      "detail" in data &&
      typeof data.detail === "string"
        ? data.detail
        : "请求失败，请检查填写内容后重试",
    );
  }
  return response;
}

/** 读取后端响应模型约束的概览，接收取消信号以支持组件卸载清理。 */
export async function readDashboard(signal: AbortSignal): Promise<Dashboard> {
  const response = await request("dashboard", "GET", undefined, signal);
  return response.json();
}
/** 根据是否存在来源 ID 选择新建或更新，只等待服务端确认，不在客户端伪造结果。 */
export async function saveSource(body: SourceBody, id?: string): Promise<void> {
  await request(id ? `sources/${id}` : "sources", id ? "PUT" : "POST", body);
}
/** 请求移除指定来源配置；历史消息的保留由后端事务服务保证。 */
export async function deleteSource(id: string): Promise<void> {
  await request(`sources/${id}`, "DELETE");
}
