/** PC 工作台路由：组合静态导航与客户端采集面板，不承担请求逻辑。 */
import { CollectorDashboard } from "@/features/collector/dashboard";
import { Sidebar } from "@/features/collector/sidebar";

/** 渲染桌面双栏工作区；当前阶段不提供手机或平板专用布局。 */
export default function DashboardPage() {
  return (
    <div className="flex min-h-screen min-w-[1180px]">
      <Sidebar />
      <CollectorDashboard />
    </div>
  );
}
