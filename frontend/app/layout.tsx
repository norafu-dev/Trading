/** 全局文档布局和面板元数据入口，统一加载主题样式。 */
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Signal Desk · 消息采集",
  description: "Discord 采集来源与 Collector 运行监控",
};

/** 设置页面中文语言、元数据与全局样式，为所有路由提供基础文档结构。 */
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
