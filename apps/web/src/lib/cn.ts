import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind class names without color hard-coding. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
