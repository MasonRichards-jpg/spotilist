import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export const STATUS_LABELS: Record<string, string> = {
  listening: "Listening",
  completed: "Completed",
  plan_to_listen: "Plan to Listen",
  dropped: "Dropped",
}

export const STATUS_COLORS: Record<string, string> = {
  listening: "text-spotify-green",
  completed: "text-blue-400",
  plan_to_listen: "text-yellow-400",
  dropped: "text-red-400",
}

export function formatDuration(ms: number): string {
  const minutes = Math.floor(ms / 60000)
  const seconds = Math.floor((ms % 60000) / 1000)
  return `${minutes}:${seconds.toString().padStart(2, "0")}`
}
