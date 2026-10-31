import { useId } from "react";

import type { ConfidenceBucket, IntentStat, VolumePoint } from "../lib/types";
import { cn, formatDay, intentTone, percent } from "../lib/format";

export function VolumeChart({ data }: { data: VolumePoint[] }) {
  const gradientId = useId().replace(/:/g, "");
  if (!data.length) {
    return <div className="py-16 text-center text-[12px] text-muted">No message volume yet.</div>;
  }

  const width = 760;
  const height = 240;
  const left = 34;
  const right = 12;
  const top = 16;
  const bottom = 28;
  const innerWidth = width - left - right;
  const innerHeight = height - top - bottom;
  const peak = Math.max(1, ...data.map((point) => Math.max(point.inbound, point.outbound)));
  const max = Math.ceil(peak / 5) * 5;
  const step = data.length > 1 ? innerWidth / (data.length - 1) : 0;

  const x = (index: number) => left + index * step;
  const y = (value: number) => top + innerHeight - (value / max) * innerHeight;

  const line = (key: "inbound" | "outbound") =>
    data
      .map((point, index) => `${index === 0 ? "M" : "L"} ${x(index).toFixed(2)} ${y(point[key]).toFixed(2)}`)
      .join(" ");

  const inboundLine = line("inbound");
  const outboundLine = line("outbound");
  const area = `${inboundLine} L ${x(data.length - 1).toFixed(2)} ${top + innerHeight} L ${left} ${
    top + innerHeight
  } Z`;
  const labelEvery = Math.max(1, Math.ceil(data.length / 7));
  const ticks = [0, 0.5, 1].map((fraction) => Math.round(max * fraction));

  return (
    <div>
      <div className="mb-4 flex items-center gap-5 text-[11px] font-semibold text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded-full bg-clay" /> Inbound
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded-full bg-moss" /> Outbound
        </span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full overflow-visible"
        role="img"
        aria-label="Inbound and outbound message volume"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#AB4E28" stopOpacity="0.14" />
            <stop offset="100%" stopColor="#AB4E28" stopOpacity="0" />
          </linearGradient>
        </defs>

        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={left}
              x2={width - right}
              y1={y(tick)}
              y2={y(tick)}
              stroke="#E3DED2"
              strokeDasharray={tick === 0 ? undefined : "3 5"}
            />
            <text x={left - 9} y={y(tick) + 3} textAnchor="end" fontSize="9" fill="#8A867B">
              {tick}
            </text>
          </g>
        ))}

        <path d={area} fill={`url(#${gradientId})`} />
        <path d={inboundLine} fill="none" stroke="#AB4E28" strokeWidth="2.25" strokeLinejoin="round" strokeLinecap="round" />
        <path
          d={outboundLine}
          fill="none"
          stroke="#3D5C49"
          strokeWidth="1.75"
          strokeDasharray="5 4"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {data.map((point, index) => (
          <g key={point.date}>
            {(data.length <= 16 || index === data.length - 1) && (
              <circle
                cx={x(index)}
                cy={y(point.inbound)}
                r="2.4"
                fill="#FFFDF8"
                stroke="#AB4E28"
                strokeWidth="1.6"
              >
                <title>
                  {formatDay(point.date)}: {point.inbound} inbound, {point.outbound} outbound
                </title>
              </circle>
            )}
            {index % labelEvery === 0 && (
              <text
                x={x(index)}
                y={height - 7}
                textAnchor="middle"
                fontSize="9"
                fill="#8A867B"
              >
                {formatDay(point.date)}
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}

export function IntentBars({ data }: { data: IntentStat[] }) {
  const sorted = [...data].sort((a, b) => b.count - a.count);
  const max = Math.max(1, ...sorted.map((item) => item.count));
  if (!sorted.some((item) => item.count > 0)) {
    return <div className="py-12 text-center text-[12px] text-muted">No intent predictions yet.</div>;
  }
  return (
    <div className="space-y-3.5">
      {sorted.map((item) => (
        <div key={item.intent}>
          <div className="mb-1.5 flex items-center justify-between gap-3">
            <span className="inline-flex min-w-0 items-center gap-2">
              <span className={cn("h-2 w-2 rounded-[2px]", intentTone(item.intent))} />
              <span className="truncate text-[11px] font-semibold capitalize text-ink-soft">
                {item.intent.replace(/_/g, " ")}
              </span>
            </span>
            <span className="shrink-0 text-[10px] tabular-nums text-muted">
              {percent(item.share)} · {item.count}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-line/55">
            <div
              className="h-full rounded-full bg-ink/80 transition-all duration-700"
              style={{ width: `${Math.max(item.count ? 2 : 0, (item.count / max) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ConfidenceChart({
  data,
  threshold = 0.8,
}: {
  data: ConfidenceBucket[];
  threshold?: number;
}) {
  const max = Math.max(1, ...data.map((item) => item.count));
  const total = data.reduce((sum, item) => sum + item.count, 0);
  if (!total) {
    return <div className="py-12 text-center text-[12px] text-muted">No confidence samples yet.</div>;
  }
  return (
    <div>
      <div className="relative flex h-32 items-end gap-1.5">
        {data.map((item, index) => {
          const lower = index / 10;
          const tone =
            lower >= threshold
              ? "bg-moss/85"
              : lower >= threshold - 0.2
                ? "bg-amber/75"
                : "bg-clay/55";
          return (
            <div key={item.bucket} className="group relative flex h-full flex-1 items-end">
              <div
                className={cn(
                  "w-full rounded-t-[3px] transition-all duration-500 hover:opacity-80",
                  tone,
                )}
                style={{ height: `${Math.max(item.count ? 3 : 0, (item.count / max) * 100)}%` }}
                title={`${item.bucket}: ${item.count}`}
              />
            </div>
          );
        })}
        <div
          className="pointer-events-none absolute -top-1 bottom-0 border-l border-dashed border-ink/40"
          style={{ left: `${threshold * 100}%` }}
        >
          <span className="absolute -top-4 left-1 whitespace-nowrap text-[9px] font-semibold uppercase tracking-[0.08em] text-muted">
            Handoff
          </span>
        </div>
      </div>
      <div className="mt-2 flex justify-between border-t border-line pt-1.5 text-[9px] tabular-nums text-muted">
        <span>0.0</span>
        <span>0.5</span>
        <span>1.0</span>
      </div>
    </div>
  );
}

export function DriftScale({
  value,
  threshold,
}: {
  value: number;
  threshold: number;
}) {
  const width = Math.min(100, (value / Math.max(threshold * 2, 0.01)) * 100);
  return (
    <div>
      <div className="relative h-2 overflow-hidden rounded-full bg-line">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-700",
            value >= threshold ? "bg-danger" : "bg-moss",
          )}
          style={{ width: `${Math.max(value ? 2 : 0, width)}%` }}
        />
        <span
          className="absolute top-0 h-full border-l border-dashed border-ink/35"
          style={{ left: `${(threshold / Math.max(threshold * 2, 0.01)) * 100}%` }}
        />
      </div>
      <div className="mt-2 flex justify-between text-[10px] text-muted">
        <span>TVD {value.toFixed(3)}</span>
        <span>threshold {threshold.toFixed(2)}</span>
      </div>
    </div>
  );
}
