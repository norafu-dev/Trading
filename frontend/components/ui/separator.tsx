/** shadcn/ui separator 基础组件，来自官方 registry；在此集中维护样式与可访问交互。 */
"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Separator as SeparatorPrimitive } from "radix-ui";

/** 渲染语义分隔线，可通过 orientation 选择方向。 */
function Separator({
  className,
  orientation = "horizontal",
  decorative = true,
  ...props
}: React.ComponentProps<typeof SeparatorPrimitive.Root>) {
  return (
    <SeparatorPrimitive.Root
      data-slot="separator"
      decorative={decorative}
      orientation={orientation}
      className={cn(
        "shrink-0 bg-border data-[orientation=horizontal]:h-px data-[orientation=horizontal]:w-full data-[orientation=vertical]:h-full data-[orientation=vertical]:w-px",
        className,
      )}
      {...props}
    />
  );
}

export { Separator };
