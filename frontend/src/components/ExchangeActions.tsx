import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, History, Scale, XCircle } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiPost } from "@/lib/api";
import { EXCHANGE_STATUS_LABEL, extractErrorMessage, money, shortDate } from "@/lib/format";
import type { CounterofferPayload, ExchangeDetail } from "@/lib/types";

const EVENT_LABEL: Record<string, string> = {
  proposed: "Proposed",
  approved: "Approved",
  counteroffer: "Counteroffer",
  changes_requested: "Changes requested",
  status_changed: "Status changed",
  rejected: "Rejected",
  cancelled: "Cancelled",
  expired: "Expired",
  fulfilment_confirmed: "Fulfilment confirmed",
  completed: "Completed",
  disputed: "Dispute opened",
  dispute_resolution_vote: "Marked dispute resolved",
  dispute_resolved: "Dispute resolved",
  admin_cancelled: "Cancelled by admin",
};

/** Lifecycle actions the server allows this viewer right now, plus the audit trail. */
export default function ExchangeActions({ detail, viewerId }: { detail: ExchangeDetail; viewerId: string }) {
  const queryClient = useQueryClient();
  const { exchange, events } = detail;
  const can = (action: string) => exchange.allowed_actions.includes(action as never);
  const names = Object.fromEntries(exchange.participants.map((p) => [p.user_id, p.user?.name ?? "Trader"]));

  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(exchange.participants.map((p) => [p.gives_listing_id, String(p.value_given)])),
  );
  const [message, setMessage] = useState("");
  const [reason, setReason] = useState("");
  const [showCounter, setShowCounter] = useState(false);

  const act = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) => apiPost<ExchangeDetail>(`/v1/exchanges/${exchange.id}/${path}`, body ?? {}),
    onSuccess: async (data, vars) => {
      queryClient.setQueryData(["exchange", exchange.id], data);
      await queryClient.invalidateQueries({ queryKey: ["exchanges"] });
      toast.success(`Exchange is now ${EXCHANGE_STATUS_LABEL[data.exchange.status] ?? data.exchange.status}`);
      if (vars.path === "counteroffer") setShowCounter(false);
      setMessage("");
      setReason("");
    },
    onError: (error) => toast.error(extractErrorMessage(error, "That action is not allowed right now")),
  });

  const submitCounter = () => {
    const agreed: Record<string, number> = {};
    for (const p of exchange.participants) {
      const next = Number(values[p.gives_listing_id]);
      if (!Number.isFinite(next) || next <= 0) {
        toast.error("Every agreed value must be a positive number");
        return;
      }
      if (Math.abs(next - p.value_given) > 0.004) agreed[p.gives_listing_id] = next;
    }
    if (!Object.keys(agreed).length) {
      toast.error("Change at least one value to send a counteroffer");
      return;
    }
    const body: CounterofferPayload = { agreed_values: agreed, message: message.trim() || "Updated terms" };
    act.mutate({ path: "counteroffer", body });
  };

  return (
    <section className="bx-panel space-y-5 p-6" data-testid="exchange-actions-panel">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-heading text-lg font-semibold text-slate-900">Proposal revision {exchange.revision}</h2>
          <p className="text-xs text-slate-500" data-testid="exchange-actions-revision-note">
            Everyone must approve this exact revision. Any counteroffer resets all approvals.
            {exchange.expires_at && ["proposed", "pending_approval"].includes(exchange.status)
              ? ` Expires ${shortDate(exchange.expires_at)} without full approval.`
              : ""}
          </p>
        </div>
      </div>

      {exchange.status === "disputed" && exchange.dispute ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700" data-testid="exchange-actions-dispute-banner">
          <p className="font-medium">Disputed by {names[exchange.dispute.opened_by] ?? "a participant"}</p>
          <p>{exchange.dispute.reason}</p>
          <p className="mt-1 text-xs">
            Resolved by {exchange.dispute.resolved_by.length} of {exchange.participants.length}. An admin can also resume or cancel it.
          </p>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {can("counteroffer") ? (
          <Button variant="outline" size="sm" className="rounded-xl" onClick={() => setShowCounter((v) => !v)} data-testid="exchange-actions-counteroffer-toggle">
            <Scale className="size-4" aria-hidden /> Counteroffer
          </Button>
        ) : null}
        {can("complete") ? (
          <Button size="sm" className="rounded-xl bg-green-600 hover:bg-green-700" disabled={act.isPending} onClick={() => act.mutate({ path: "complete" })} data-testid="exchange-actions-complete-button">
            <CheckCircle2 className="size-4" aria-hidden /> Complete exchange
          </Button>
        ) : null}
        {can("resolve_dispute") ? (
          <Button size="sm" variant="outline" className="rounded-xl" disabled={act.isPending} onClick={() => act.mutate({ path: "dispute/resolve" })} data-testid="exchange-actions-resolve-button">
            Mark dispute resolved
          </Button>
        ) : null}
      </div>

      {showCounter && can("counteroffer") ? (
        <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4" data-testid="exchange-actions-counteroffer-form">
          <p className="text-xs text-slate-500">Set the agreed value of each item. Balances are recalculated on the server.</p>
          {exchange.participants.map((p) => (
            <label key={p.gives_listing_id} className="flex items-center justify-between gap-3 text-sm">
              <span className="text-slate-700">
                {p.gives_listing?.title ?? "Listing"} <span className="text-slate-400">· {names[p.user_id]}</span>
              </span>
              <Input
                type="number"
                min={1}
                step="0.01"
                className="w-32 bg-white"
                value={values[p.gives_listing_id] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [p.gives_listing_id]: e.target.value }))}
                data-testid={`exchange-actions-counter-value-${p.gives_listing_id}`}
              />
            </label>
          ))}
          <Textarea value={message} placeholder="Why these values?" onChange={(e) => setMessage(e.target.value)} data-testid="exchange-actions-counter-message" />
          <Button size="sm" className="rounded-xl bg-blue-600 hover:bg-blue-700" disabled={act.isPending} onClick={submitCounter} data-testid="exchange-actions-counter-submit">
            Send counteroffer
          </Button>
        </div>
      ) : null}

      {can("reject") || can("dispute") ? (
        <div className="space-y-2 border-t border-slate-100 pt-4">
          <Input value={reason} placeholder="Reason (shared with the other traders)" onChange={(e) => setReason(e.target.value)} data-testid="exchange-actions-reason-input" />
          <div className="flex flex-wrap gap-2">
            {can("reject") ? (
              <Button size="sm" variant="outline" className="rounded-xl border-red-200 text-red-600 hover:bg-red-50" disabled={act.isPending}
                onClick={() => act.mutate({ path: "reject", body: { reason } })} data-testid="exchange-actions-reject-button">
                <XCircle className="size-4" aria-hidden /> Reject proposal
              </Button>
            ) : null}
            {can("dispute") ? (
              <Button size="sm" variant="outline" className="rounded-xl border-amber-200 text-amber-700 hover:bg-amber-50" disabled={act.isPending || reason.trim().length < 3}
                onClick={() => act.mutate({ path: "dispute", body: { reason } })} data-testid="exchange-actions-dispute-button">
                <AlertTriangle className="size-4" aria-hidden /> Open dispute
              </Button>
            ) : null}
          </div>
          {can("reject") ? <p className="text-xs text-slate-400">Rejecting ends this proposal and this cycle won't be suggested again.</p> : null}
        </div>
      ) : null}

      <div className="border-t border-slate-100 pt-4">
        <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-slate-500">
          <History className="size-3.5" aria-hidden /> Activity
        </p>
        <ol className="space-y-1.5" data-testid="exchange-actions-events">
          {events.slice(-8).reverse().map((event) => (
            <li key={event.id} className="flex justify-between gap-3 text-xs" data-testid={`exchange-event-${event.id}`}>
              <span className="text-slate-700">
                {EVENT_LABEL[event.kind] ?? event.kind}
                {event.actor_id ? ` · ${event.actor_id === viewerId ? "you" : names[event.actor_id] ?? "admin"}` : ""}
                {event.kind === "status_changed" ? ` → ${EXCHANGE_STATUS_LABEL[event.to_status] ?? event.to_status}` : ""}
                <span className="text-slate-400"> · r{event.revision}</span>
              </span>
              <span className="shrink-0 font-mono text-slate-400">{shortDate(event.created_at)}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
