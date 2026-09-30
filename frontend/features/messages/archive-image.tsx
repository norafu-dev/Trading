/** 展示归档图片及失败占位；稳定 API 地址每次读取时换取新的 R2 签名。 */
import { useState } from "react";
import Image from "next/image";
import { ImageOff } from "lucide-react";
import { Button } from "@/components/ui/button";

/** 保留原图比例，下载失败时解释状态，允许重新读取而不显示破损图片图标。 */
export function ArchiveImage({
  url,
  alt,
  status,
  error,
}: {
  url: string;
  alt: string;
  status: string | null;
  error: string | null;
}) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const imageUrl = url.startsWith("/api/media/") ? `${url}?reload=${attempt}` : url;
  const failed = failedUrl === imageUrl;

  /** 清除当前加载失败状态；归档地址再次请求时由后端生成新签名。 */
  function reload() {
    setFailedUrl(null);
    setAttempt((previous) => previous + 1);
  }

  /** 记录实际失败的地址，切换到 R2 地址后旧失败状态不会继续遮挡图片。 */
  function imageFailed() {
    setFailedUrl(imageUrl);
  }

  return (
    <div className="mt-2 max-w-[720px]">
      {failed ? (
        <div className="flex min-h-28 items-center gap-3 rounded-md border bg-muted p-4 text-sm text-muted-foreground">
          <ImageOff className="size-6 shrink-0" />
          <div className="space-y-1">
            <p>图片暂时无法显示</p>
            <p className="text-xs">
              {error ||
                (status === "stored"
                  ? "请检查网络或 R2 读取配置，然后重新加载。"
                  : "Discord 链接可能已过期，等待归档或在图片归档面板检查配置。")}
            </p>
            <Button variant="outline" size="sm" onClick={reload}>
              重新加载
            </Button>
          </div>
        </div>
      ) : (
        <a href={url} target="_blank" rel="noreferrer">
          <Image
            key={imageUrl}
            src={imageUrl}
            alt={alt}
            width={720}
            height={480}
            unoptimized
            onError={imageFailed}
            className="max-h-[520px] w-auto max-w-full rounded-md object-contain"
          />
        </a>
      )}
      {status && status !== "stored" && (
        <p className="mt-1 text-xs text-muted-foreground">
          {status === "failed"
            ? `归档失败：${error || "请到归档面板重试"}`
            : "图片等待归档，暂使用 Discord 链接"}
        </p>
      )}
    </div>
  );
}
