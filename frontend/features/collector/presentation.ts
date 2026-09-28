/** 将采集业务状态转换为文案、时间和 shadcn 状态标签变体。 */
export const states: Record<string, { label: string; tone: string; hint: string }> = {
  connected: {
    label: "Discord 已连接",
    tone: "green",
    hint: "正在监听通过校验的采集来源",
  },
  connecting: {
    label: "正在连接",
    tone: "amber",
    hint: "Collector 正在建立 Discord 连接",
  },
  missing_token: {
    label: "等待配置 Token",
    tone: "amber",
    hint: "服务已就绪，配置 Discord Token 后即可开始监听。",
  },
  disconnected: {
    label: "连接已断开",
    tone: "amber",
    hint: "正在等待 Discord 会话恢复，期间的消息暂不自动补采。",
  },
  stale: {
    label: "心跳已过期",
    tone: "red",
    hint: "超过 30 秒未收到心跳，请检查 Collector 容器。",
  },
  error: {
    label: "运行异常",
    tone: "red",
    hint: "Collector 已停止处理，请检查下面的错误信息。",
  },
  stopped: {
    label: "服务未运行",
    tone: "muted",
    hint: "启动 Collector 服务后，这里会显示实时运行状态。",
  },
};

/** 把服务端时间转换成本地时间；full 控制是否附加月日，空值显示占位符。 */
export function time(value: string | null | undefined, full = false) {
  if (!value) return "—";
  return new Date(value).toLocaleString(
    "zh-CN",
    full
      ? {
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        }
      : {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        },
  );
}

/** 优先解释是否停用，再把来源校验状态转换为面板文案和语义颜色。 */
export function sourceStatus(source: { enabled: boolean; status: string }) {
  if (!source.enabled) return { tone: "muted", label: "已停用" };
  if (source.status === "error") return { tone: "red", label: "校验失败" };
  if (source.status === "ready") return { tone: "green", label: "已校验" };
  return { tone: "amber", label: "待校验" };
}
/** 把事件错误级别转换为统一状态颜色，不依赖原始日志内容。 */
export function eventTone(level: string) {
  if (level === "error") return "red";
  if (level === "warning") return "amber";
  return "green";
}
/** 只根据 API 读取结果描述管理服务连接，区别于 Discord 连接状态。 */
export function connectionStatus(hasData: boolean, error: string) {
  if (error) return { tone: "red", label: "连接中断" };
  if (hasData) return { tone: "green", label: "管理服务在线" };
  return { tone: "muted", label: "连接中" };
}

/** 将业务状态颜色映射到集中维护的 shadcn Badge 变体。 */
export function badgeVariant(
  tone: string,
): "success" | "warning" | "destructive" | "secondary" {
  if (tone === "green") return "success";
  if (tone === "amber") return "warning";
  if (tone === "red") return "destructive";
  return "secondary";
}
