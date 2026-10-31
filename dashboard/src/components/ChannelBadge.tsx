import { MessageCircle, Instagram } from "lucide-react";

import { cn } from "../lib/format";
import type { Channel } from "../lib/types";

export function ChannelBadge({ channel, className }: { channel: Channel; className?: string }) {
  const isWhatsApp = channel === "whatsapp";
  const Icon = isWhatsApp ? MessageCircle : Instagram;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-[0.08em]",
        isWhatsApp ? "text-moss" : "text-clay",
        className,
      )}
      title={isWhatsApp ? "WhatsApp" : "Instagram"}
    >
      <Icon size={12} strokeWidth={1.9} />
      {isWhatsApp ? "WhatsApp" : "Instagram"}
    </span>
  );
}
