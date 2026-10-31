export function cn(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(" ");
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function initials(name?: string | null): string {
  if (!name) return "?";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("");
}

export function compactNumber(value: number): string {
  return new Intl.NumberFormat("en", {
    notation: value >= 10_000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
}

export function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function relativeTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value.endsWith("Z") ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return "—";
  const diffSeconds = Math.round((date.getTime() - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const ranges: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 60 * 60 * 24 * 365],
    ["month", 60 * 60 * 24 * 30],
    ["week", 60 * 60 * 24 * 7],
    ["day", 60 * 60 * 24],
    ["hour", 60 * 60],
    ["minute", 60],
  ];
  for (const [unit, seconds] of ranges) {
    if (Math.abs(diffSeconds) >= seconds) {
      return formatter.format(Math.round(diffSeconds / seconds), unit);
    }
  }
  return "just now";
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value.endsWith("Z") ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatTime(value: string): string {
  const date = new Date(value.endsWith("Z") ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatDay(value: string): string {
  const date = new Date(`${value}T12:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "short" }).format(date);
}

export function ageHours(value: string): number {
  const date = new Date(value.endsWith("Z") ? value : `${value}Z`);
  return Math.max(0, (Date.now() - date.getTime()) / 3_600_000);
}

export function maskExternal(value: string): string {
  if (value.length <= 6) return value;
  return `${value.slice(0, 3)}…${value.slice(-4)}`;
}

export const INTENT_TONES: Record<string, string> = {
  greeting: "bg-[#EDE7D9] text-[#6A5A37]",
  order_status: "bg-[#DDE7E8] text-[#2D5B60]",
  return_refund: "bg-[#F3E2D8] text-[#8E4A2C]",
  product_info: "bg-[#E3E8DB] text-[#4C5F3A]",
  pricing: "bg-[#F4E9C9] text-[#7E611D]",
  complaint: "bg-[#F5DCD8] text-[#903C31]",
  human_agent: "bg-[#E6E1F0] text-[#5B487E]",
  goodbye: "bg-[#E8E5DD] text-[#5C584D]",
  other: "bg-[#E5E5E1] text-[#5E5E56]",
};

export function intentTone(intent?: string | null): string {
  return INTENT_TONES[intent || ""] || "bg-paper text-muted";
}

export function priorityTone(priority: string): string {
  switch (priority) {
    case "urgent":
      return "bg-danger-soft text-danger border-danger/20";
    case "high":
      return "bg-amber-soft text-amber border-amber/20";
    case "low":
      return "bg-moss-soft text-moss border-moss/15";
    default:
      return "bg-paper text-muted border-line";
  }
}

export function statusTone(status: string): string {
  switch (status) {
    case "needs_human":
      return "bg-amber-soft text-amber";
    case "resolved":
      return "bg-moss-soft text-moss";
    case "open":
      return "bg-amber-soft text-amber";
    case "assigned":
      return "bg-[#E6E1F0] text-[#5B487E]";
    default:
      return "bg-ink/[0.055] text-ink-soft";
  }
}

export function confidenceTone(value?: number | null): string {
  if (value === null || value === undefined) return "text-muted";
  if (value >= 0.9) return "text-moss";
  if (value >= 0.8) return "text-ink-soft";
  if (value >= 0.6) return "text-amber";
  return "text-danger";
}

export function secondsAgo(timestamp: number): string {
  const seconds = Math.round((Date.now() - timestamp) / 1000);
  if (seconds < 10) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  return `${Math.round(seconds / 60)}m ago`;
}
