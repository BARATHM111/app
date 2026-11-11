import type { ExchangeStatus, ListingStatus, ListingType } from "@/lib/types";
import { EXCHANGE_STATUS_LABEL } from "@/lib/format";

const TYPE_STYLE: Record<ListingType, string> = {
  goods: "bx-badge-goods",
  services: "bx-badge-services",
};

export function TypeBadge({ type, testId }: { type: ListingType; testId?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[11px] uppercase tracking-wide ${TYPE_STYLE[type]}`}
      data-testid={testId ?? `type-badge-${type}`}
    >
      {type === "goods" ? "Goods" : "Service"}
    </span>
  );
}

export function CategoryChip({ category }: { category: string }) {
  return (
    <span className="inline-flex items-center rounded-md border border-slate-200 px-2 py-0.5 text-[11px] text-slate-700">
      {category}
    </span>
  );
}

export function StatusBadge({ status }: { status: ExchangeStatus | ListingStatus }) {
  const tone: Record<string, string> = {
    active: "bg-green-50 text-green-600",
    draft: "bg-slate-100 text-slate-700",
    paused: "bg-amber-50 text-amber-500",
    reserved: "bg-blue-50 text-blue-600",
    traded: "bg-slate-100 text-slate-700",
    archived: "bg-slate-100 text-slate-500",
    proposed: "bg-amber-50 text-amber-700",
    pending_approval: "bg-amber-50 text-amber-700",
    approved: "bg-blue-50 text-blue-700",
    payment_pending: "bg-violet-50 text-violet-700",
    ready_for_fulfillment: "bg-blue-50 text-blue-700",
    fulfillment_in_progress: "bg-blue-50 text-blue-700",
    completed: "bx-badge-cycle",
    rejected: "bg-red-50 text-red-600",
    cancelled: "bg-red-50 text-red-600",
    disputed: "bg-red-50 text-red-700",
    expired: "bg-slate-100 text-slate-500",
  };
  const label = EXCHANGE_STATUS_LABEL[status] ?? status.replace(/_/g, " ");
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[11px] uppercase tracking-wide ${
        tone[status] ?? "bg-slate-100 text-slate-700"
      }`}
      data-testid={`status-badge-${status}`}
    >
      {label}
    </span>
  );
}

export function CycleSizeBadge({ size }: { size: number }) {
  return (
    <span className="bx-badge-cycle inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[11px] uppercase tracking-wide">
      {size}-party cycle
    </span>
  );
}
