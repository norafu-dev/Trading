/** PC 消息浏览路由，组合应用导航与 Discord 风格的只读消息工作区。 */
import { Sidebar } from "@/features/collector/sidebar";
import { MessageBrowser } from "@/features/messages/message-browser";

/** 保持管理面板入口，并为消息浏览提供占满视口高度的独立页面。 */
export default function MessagesPage() {
  return (
    <div className="flex h-screen min-w-[1180px] overflow-hidden">
      <Sidebar active="messages" />
      <MessageBrowser />
    </div>
  );
}
