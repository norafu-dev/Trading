/** Next.js 生产构建配置；通过同源代理连接 Docker 内部 FastAPI 服务。 */
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "cdn.discordapp.com" },
      { protocol: "https", hostname: "media.discordapp.net" },
      { protocol: "https", hostname: "images-ext-1.discordapp.net" },
      { protocol: "https", hostname: "images-ext-2.discordapp.net" },
    ],
  },
  /** 将浏览器的 /api 请求代理到容器内 API，避免额外暴露后端端口。 */
  async rewrites() {
    return [{ source: "/api/:path*", destination: "http://api:8000/api/:path*" }];
  },
};
export default nextConfig;
