import type { Cycle } from "@/lib/types";
import { money, balanceText } from "@/lib/format";

const NODE_W = 236;
const NODE_H = 104;
const VIEW_W = 800;
const VIEW_H = 430;

const LAYOUTS: Record<number, { x: number; y: number }[]> = {
  2: [
    { x: 200, y: 190 },
    { x: 600, y: 190 },
  ],
  3: [
    { x: 400, y: 100 },
    { x: 165, y: 330 },
    { x: 635, y: 330 },
  ],
};

function clip(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function borderPoint(from: { x: number; y: number }, to: { x: number; y: number }) {
  const dx = to.x - from.x || 0.001;
  const dy = to.y - from.y || 0.001;
  const halfW = NODE_W / 2 + 14;
  const halfH = NODE_H / 2 + 14;
  const scale = Math.min(halfW / Math.abs(dx), halfH / Math.abs(dy));
  return { x: from.x + dx * scale, y: from.y + dy * scale };
}

function balanceTone(balance: number): string {
  if (balance > 0.005) return "#D97706";
  if (balance < -0.005) return "#2563EB";
  return "#16A34A";
}

/** Deterministic, data-driven cycle diagram — 2 nodes in a line, 3 nodes in a loop. */
export default function CycleGraph({ cycle }: { cycle: Cycle }) {
  const points = LAYOUTS[cycle.cycle_type] ?? LAYOUTS[2];
  const size = cycle.participants.length;

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        role="img"
        aria-label={`${size}-party barter cycle with ${size} participants`}
        className="mx-auto h-auto w-full min-w-[560px] max-w-[820px]"
        data-testid={`cycle-graph-${cycle.key}`}
      >
        <defs>
          <marker id={`bx-arrow-${cycle.key}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#2563EB" />
          </marker>
        </defs>

        {cycle.participants.map((participant, index) => {
          const from = points[index];
          const to = points[(index + 1) % size];
          const start = borderPoint(from, to);
          const end = borderPoint(to, from);
          const midX = (start.x + end.x) / 2;
          const midY = (start.y + end.y) / 2;
          const dx = end.x - start.x;
          const dy = end.y - start.y;
          const length = Math.hypot(dx, dy) || 1;
          const bend = cycle.cycle_type === 2 ? 52 : 34;
          const controlX = midX - (dy / length) * bend;
          const controlY = midY + (dx / length) * bend;
          const path = `M ${start.x} ${start.y} Q ${controlX} ${controlY} ${end.x} ${end.y}`;
          const labelX = (start.x + 2 * controlX + end.x) / 4;
          const labelY = (start.y + 2 * controlY + end.y) / 4;

          return (
            <g key={`${participant.user_id}-edge`} data-testid={`cycle-edge-${cycle.key}-${index}`}>
              <path d={path} fill="none" stroke="#E2E8F0" strokeWidth="9" strokeLinecap="round" />
              <path
                d={path}
                fill="none"
                stroke="#2563EB"
                strokeWidth="2"
                strokeDasharray="8 8"
                markerEnd={`url(#bx-arrow-${cycle.key})`}
                className="bx-flow"
              />
              <rect
                x={labelX - 46}
                y={labelY - 13}
                width="92"
                height="26"
                rx="13"
                fill="#FFFFFF"
                stroke="#CBD5E1"
                strokeWidth="1"
              />
              <text
                x={labelX}
                y={labelY + 4}
                textAnchor="middle"
                fill="#1D4ED8"
                fontSize="12"
                fontFamily="IBM Plex Mono, monospace"
              >
                {money(participant.gives_value, cycle.participants[0]?.currency ?? "USD")}
              </text>
            </g>
          );
        })}

        {cycle.participants.map((participant, index) => {
          const point = points[index];
          const x = point.x - NODE_W / 2;
          const y = point.y - NODE_H / 2;
          return (
            <g key={participant.user_id} data-testid={`cycle-node-${participant.user_id}`}>
              <rect
                x={x}
                y={y}
                width={NODE_W}
                height={NODE_H}
                rx="16"
                fill="#FFFFFF"
                stroke="#CBD5E1"
                strokeWidth="1.5"
              />
              <text x={point.x} y={y + 26} textAnchor="middle" fill="#0F172A" fontSize="15" fontWeight="600" fontFamily="Outfit Variable, sans-serif">
                {clip(participant.user_name, 26)}
              </text>
              <text x={point.x} y={y + 46} textAnchor="middle" fill="#64748B" fontSize="11" fontFamily="DM Sans Variable, sans-serif">
                gives: {clip(participant.gives_listing_title, 30)}
              </text>
              <text x={point.x} y={y + 64} textAnchor="middle" fill="#64748B" fontSize="11" fontFamily="DM Sans Variable, sans-serif">
                gets: {clip(participant.receives_listing_title, 30)}
              </text>
              <text
                x={point.x}
                y={y + 88}
                textAnchor="middle"
                fill={balanceTone(participant.balance_amount)}
                fontSize="12"
                fontFamily="IBM Plex Mono, monospace"
              >
                {balanceText(participant.balance_amount, participant.currency)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
