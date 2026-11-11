// Presentation helpers. Money and dates are formatted for display only — the backend owns
// every calculation and every timestamp.

export function money(amount: number, currency = "USD"): string {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

export function shortDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

export function dateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

/** Positive balance = this trader owes a balancing payment. */
export function balanceText(balance: number, currency = "USD"): string {
  if (balance > 0.005) return `owes ${money(balance, currency)}`;
  if (balance < -0.005) return `is owed ${money(Math.abs(balance), currency)}`;
  return "balanced";
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export const EXCHANGE_STATUS_LABEL: Record<string, string> = {
  discovered: "Discovered",
  proposed: "Proposed",
  pending_approval: "Pending approval",
  approved: "Approved",
  payment_pending: "Payment pending",
  ready_for_fulfillment: "Ready for fulfilment",
  fulfillment_in_progress: "Fulfilment in progress",
  completed: "Completed",
  rejected: "Rejected",
  cancelled: "Cancelled",
  disputed: "Disputed",
  expired: "Expired",
};

export function extractErrorMessage(error: unknown, fallback = "Something went wrong"): string {
  if (error && typeof error === "object" && "body" in error) {
    const body = (error as { body?: unknown }).body;
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail?: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
