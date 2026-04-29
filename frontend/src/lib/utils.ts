import { twMerge } from "tailwind-merge";
import { clsx as _clsx, type ClassValue } from "clsx";

/** Concatenate class names with Tailwind-aware dedupe. */
export function clsx(...inputs: ClassValue[]): string {
  return twMerge(_clsx(inputs));
}
