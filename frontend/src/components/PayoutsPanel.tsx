import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Send } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiGet, apiPost } from "@/lib/api";
import { extractErrorMessage, money } from "@/lib/format";
import type { Exchange, Payout, PayoutListResponse, PayoutStatus } from "@/lib/types";

const STATUS_TEXT: Record<PayoutStatus, string> = {
  pending: "Being prepared",
  processing: "Sent, waiting for PayPal to confirm",
  success: "Paid, confirmed by PayPal",
  unclaimed: "Held by PayPal until the email is registered",
  failed: "Failed, can be claimed again",
  blocked: "Not sent yet (PayPal not configured)",
};

const STATUS_TONE: Record<PayoutStatus, string> = {
  pending: "text-slate-700",
  processing: "text-blue-600",
  success: "text-green-600",
  unclaimed: "text-amber-700",
  failed: "text-red-600",
  blocked: "text-amber-700",
};

/** Balancing payouts to traders who are owed money. Only shown once a cycle includes someone owed money. */
export default function PayoutsPanel({ exchange, viewerId }: { exchange: Exchange; viewerId: string }) {
  const queryClient = useQueryClient();
  const owed = exchange.participants.filter((participant) => participant.balance_amount < 0);
  const viewerParticipant = exchange.participants.find((participant) => participant.user_id === viewerId);
  const viewerOwed = viewerParticipant ? -viewerParticipant.balance_amount : 0;
  const completed = exchange.status === "completed";

  const payouts = useQuery({
    queryKey: ["payouts", exchange.id],
    queryFn: () => apiGet<PayoutListResponse>(`/v1/exchanges/${exchange.id}/payouts`),
    enabled: owed.length > 0,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["payouts", exchange.id] });

  const claim = useMutation({
    mutationFn: () => apiPost<Payout>(`/v1/exchanges/${exchange.id}/payouts/claim`),
    onSuccess: async (payout) => {
      await invalidate();
      toast.success(payout.status === "success" ? "PayPal confirmed your payout" : `Payout status: ${STATUS_TEXT[payout.status]}`);
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not claim the payout")),
  });

  const refresh = useMutation({
    mutationFn: (payoutId: string) => apiPost<Payout>(`/v1/payouts/${payoutId}/refresh`),
    onSuccess: () => invalidate(),
    onError: (error) => toast.error(extractErrorMessage(error, "Could not refresh from PayPal")),
  });

  if (!owed.length) return null;

  const records = payouts.data?.payouts ?? [];
  const mine = records.find((payout) => payout.user_id === viewerId);
  const canClaim = completed && viewerOwed > 0 && (!mine || ["failed", "blocked", "pending"].includes(mine.status));

  return (
    <section className="bx-panel space-y-4 p-6" data-testid="proposal-payouts-panel">
      <div>
        <h2 className="font-heading text-lg text-slate-900">Payouts to owed traders</h2>
        <p className="text-xs text-slate-500">
          Sent automatically through PayPal Sandbox once everyone confirms fulfilment. A payout only counts as paid
          when PayPal confirms it.
        </p>
      </div>

      <ul className="space-y-2">
        {owed.map((participant) => {
          const record = records.find((payout) => payout.participant_id === participant.id);
          return (
            <li
              key={participant.id}
              className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm"
              data-testid={`proposal-payout-${participant.user_id}`}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-slate-900">{participant.user?.name ?? "Trader"}</span>
                <span className="font-mono text-slate-900">{money(-participant.balance_amount, participant.currency)}</span>
              </div>
              <p
                className={`mt-1 text-xs ${record ? STATUS_TONE[record.status] : "text-slate-500"}`}
                data-testid={`proposal-payout-${participant.user_id}-status`}
              >
                {record ? STATUS_TEXT[record.status] : completed ? "Not sent yet" : "Sent after everyone confirms fulfilment"}
              </p>
              {record?.last_error && record.status !== "success" ? (
                <p className="mt-1 text-xs text-slate-500" data-testid={`proposal-payout-${participant.user_id}-error`}>
                  {record.last_error}
                </p>
              ) : null}
              {record && record.user_id === viewerId && ["processing", "unclaimed"].includes(record.status) ? (
                <button
                  type="button"
                  onClick={() => refresh.mutate(record.id)}
                  className="mt-2 inline-flex items-center gap-1 text-xs text-blue-600 transition-colors duration-200 hover:text-blue-700"
                  data-testid={`proposal-payout-${participant.user_id}-refresh-button`}
                >
                  <RefreshCw className={`size-3 ${refresh.isPending ? "animate-spin" : ""}`} aria-hidden />
                  Check with PayPal
                </button>
              ) : null}
            </li>
          );
        })}
      </ul>

      {canClaim ? (
        <Button onClick={() => claim.mutate()} disabled={claim.isPending} className="w-full" data-testid="proposal-payout-claim-button">
          <Send className="size-4" aria-hidden />
          {claim.isPending ? "Sending…" : `Claim payout of ${money(viewerOwed, viewerParticipant?.currency ?? "USD")}`}
        </Button>
      ) : null}
    </section>
  );
}
