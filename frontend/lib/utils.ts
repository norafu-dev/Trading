/** 合并组件的条件样式，解决 Tailwind 类名冲突。 */
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** 合并条件类名，并让调用方的同类 Tailwind 样式覆盖默认值。 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
