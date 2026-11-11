import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock, MessageSquare, PackageCheck, ShieldAlert, Sparkles, Wallet, XCircle } from "lucide-react";
import { toast } from "sonner";

import { CycleSizeBadge, StatusBadge } from "@/components/Badges";
import CycleGraph from "@/components/CycleGraph";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiGet, apiPost } from "@/lib/api";
import { balanceText, dateTime, extractErrorMessage, money } from "@/lib/format";
import { useSession } from "@/lib/session";
import ExchangeActions from "@/components/ExchangeActions";
import PayoutsPanel from "@/components/PayoutsPanel";
import ReviewForm from "@/components/ReviewForm";
import TraderBadge from "@/components/TraderBadge";
import type {
  Cycle,
  DealSummaryResponse,
  Exchange,
  ExchangeDetail,
  FulfilmentResponse,
  Payment,
  PaymentConfigStatus,
  PaymentInitResponse,
  PaymentListResponse,
} from "@/lib/types";

function toCycle(exchange: Exchange): Cycle {
  return {
    key: exchange.id,
    id: exchange.id,
    status: exchange.status,
    min_edge_score: Number(exchange.value_summary.min_edge_score ?? 0),
    avg_edge_score: Number(exchange.value_summary.avg_edge_score ?? 0),
    rank: 0,
    reasons: [],
    cycle_type: exchange.cycle_type,
    participant_ids: exchange.participant_ids,
    participants: exchange.participants.map((participant) => ({
      user_id: participant.user_id,
      user_name: participant.user?.name ?? "Trader",
      gives_listing_id: participant.gives_listing_id,
      gives_listing_title: participant.gives_listing?.title ?? "Listing",
      gives_value: participant.value_given,
      receives_listing_id: participant.receives_listing_id,
      receives_listing_title: participant.receives_listing?.title ?? "Listing",
      receives_value: participant.value_received,
      balance_amount: participant.balance_amount,
      currency: participant.currency,
    })),
    total_value: exchange.value_summary.total_value ?? 0,
    total_imbalance: exchange.value_summary.total_imbalance ?? 0,
    mean_semantic_score: exchange.value_summary.mean_semantic_score ?? 0,
    edges: [],
  };
}

export default function Proposal() {
  const { id = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, isLoading } = useSession();
  const queryClient = useQueryClient();
  const [changeNote, setChangeNote] = useState("");
  const [message, setMessage] = useState("");
  const [authorised, setAuthorised] = useState(false);
  const [summary, setSummary] = useState<DealSummaryResponse | null>(null);
  const captureStarted = useRef(false);

  const detail = useQuery({
    queryKey: ["exchange", id],
    queryFn: () => apiGet<ExchangeDetail>(`/v1/exchanges/${id}`),
    enabled: Boolean(user),
    retry: false,
  });

  const paymentConfig = useQuery({
    queryKey: ["payments-config"],
    queryFn: () => apiGet<PaymentConfigStatus>("/v1/payments/config"),
    retry: false,
  });

  const myPayments = useQuery({
    queryKey: ["payments", "mine"],
    queryFn: () => apiGet<PaymentListResponse>("/v1/payments/mine"),
    enabled: Boolean(user),
    retry: false,
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["exchange", id] });
    await queryClient.invalidateQueries({ queryKey: ["exchanges"] });
    await queryClient.invalidateQueries({ queryKey: ["payments"] });
    await queryClient.invalidateQueries({ queryKey: ["notifications"] });
  };

  const approve = useMutation({
    mutationFn: () => apiPost<ExchangeDetail>(`/v1/exchanges/${id}/approve`, { decision: "approved", note: "", revision: detail.data?.exchange.revision }),
    onSuccess: async () => {
      await refresh();
      toast.success("Approval recorded for this revision");
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not record your approval")),
  });

  const requestChanges = useMutation({
    mutationFn: () => apiPost<ExchangeDetail>(`/v1/exchanges/${id}/request-changes`, { note: changeNote }),
    onSuccess: async () => {
      setChangeNote("");
      await refresh();
      toast.success("Changes requested — all approvals were reset");
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not request changes")),
  });

  const sendMessage = useMutation({
    mutationFn: (toUserId: string) =>
      apiPost<ExchangeDetail>(`/v1/exchanges/${id}/offers`, { to_user_id: toUserId, message }),
    onSuccess: async () => {
      setMessage("");
      await refresh();
      toast.success("Message sent to the other participants");
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not send that message")),
  });

  const cancel = useMutation({
    mutationFn: () => apiPost<ExchangeDetail>(`/v1/exchanges/${id}/cancel`),
    onSuccess: async () => {
      await refresh();
      await queryClient.invalidateQueries({ queryKey: ["cycles"] });
      toast.success("Exchange cancelled — listings are back on the market");
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not cancel")),
  });

  const fulfil = useMutation({
    mutationFn: () => apiPost<FulfilmentResponse>(`/v1/exchanges/${id}/fulfilment`),
    onSuccess: async (result) => {
      await refresh();
      toast.success(
        result.exchange_status === "completed"
          ? "Exchange completed — every participant confirmed"
          : "Your fulfilment is confirmed",
      );
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not confirm fulfilment")),
  });

  const startPayment = useMutation({
    mutationFn: () => {
      const back = `${window.location.origin}/proposal/${id}`;
      return apiPost<PaymentInitResponse>(`/v1/exchanges/${id}/payments`, {
        return_url: `${back}?paypal=return`,
        cancel_url: `${back}?paypal=cancel`,
      });
    },
    onSuccess: (result) => {
      toast.success("Redirecting to PayPal Sandbox to approve the payment");
      window.location.assign(result.approval_url);
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not start the payment")),
  });

  const capture = useMutation({
    mutationFn: (paymentId: string) => apiPost<Payment>(`/v1/payments/${paymentId}/capture`),
    onSuccess: async (payment) => {
      await refresh();
      if (payment.verified) toast.success("PayPal confirmed the capture — payment verified");
      else toast.error(payment.last_error ?? "PayPal did not confirm the capture");
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Capture could not be verified")),
  });

  const dealSummary = useMutation({
    mutationFn: () => apiPost<DealSummaryResponse>("/v1/ai/deal-summary", { exchange_id: id }),
    onSuccess: (data) => setSummary(data),
    onError: (error) => toast.error(extractErrorMessage(error, "The deal summary is unavailable right now")),
  });

  const exchange = detail.data?.exchange;
  const me = exchange?.my_participant ?? null;
  const myPayment = myPayments.data?.payments.find((payment) => payment.exchange_id === id) ?? null;

  // Returning from PayPal: the redirect alone proves nothing — the server captures and verifies.
  useEffect(() => {
    const flag = searchParams.get("paypal");
    if (!flag || !myPayment || captureStarted.current) return;
    captureStarted.current = true;
    if (flag === "return" && !myPayment.verified) {
      capture.mutate(myPayment.id);
    } else if (flag === "cancel") {
      // Record the abandonment server-side so the order cannot be captured later by accident.
      void apiPost(`/v1/payments/${myPayment.id}/cancel`).then(() =>
        queryClient.invalidateQueries({ queryKey: ["exchange", id] }),
      );
      toast("Payment not approved on PayPal. Nothing was charged.");
    }
    setSearchParams({}, { replace: true });
  }, [searchParams, myPayment, capture, setSearchParams]);

  if (isLoading) {
    return <div className="h-64 rounded-2xl border border-slate-200 bg-white bx-shimmer" />;
  }

  if (!user) {
    return (
      <div className="bx-panel mx-auto max-w-xl space-y-4 p-8 text-center" data-testid="proposal-signin-prompt">
        <h1 className="font-heading text-2xl text-slate-900">Sign in to open this proposal</h1>
        <p className="text-sm text-slate-500">Only participants of an exchange can see its deal room.</p>
        <Link
          to="/login"
          className="inline-flex rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-blue-600"
          data-testid="proposal-signin-link"
        >
          Sign in
        </Link>
      </div>
    );
  }

  if (detail.isLoading) {
    return <div className="h-72 rounded-2xl border border-slate-200 bg-white bx-shimmer" data-testid="proposal-loading" />;
  }

  if (detail.isError || !exchange) {
    return (
      <div className="bx-panel mx-auto max-w-xl space-y-3 p-8" data-testid="proposal-error">
        <h1 className="font-heading text-xl text-slate-900">This proposal isn't available to you</h1>
        <p className="text-sm text-slate-500">
          {extractErrorMessage(detail.error, "It may not exist, or you are not one of its participants.")}
        </p>
        <Link to="/cycles" className="text-sm font-medium text-blue-600 hover:text-blue-700" data-testid="proposal-back-to-cycles-link">
          Back to cycles →
        </Link>
      </div>
    );
  }

  const closed = ["completed", "cancelled", "rejected", "expired"].includes(exchange.status);
  const approvals = detail.data?.approvals ?? [];
  const offers = detail.data?.offers ?? [];
  const myApprovalCurrent =
    me?.approval_status === "approved" && me.approved_revision === exchange.revision;
  const owes = me ? me.balance_amount > 0.005 : false;
  const paymentPhase = ["approved", "payment_pending", "ready_for_fulfillment", "fulfillment_in_progress"].includes(exchange.status);
  const canFulfil = exchange.allowed_actions.includes("confirm_fulfilment");
  const others = exchange.participants.filter((participant) => participant.user_id !== user.id);

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <CycleSizeBadge size={exchange.cycle_type} />
            <StatusBadge status={exchange.status} />
            <span className="font-mono text-xs text-slate-500" data-testid="proposal-revision">
              revision {exchange.revision}
            </span>
          </div>
          <h1 className="font-heading text-3xl font-semibold text-slate-900">Deal room</h1>
          <p className="text-sm text-slate-500" data-testid="proposal-approval-progress">
            {exchange.approvals_current} of {exchange.approvals_required} participants approved revision{" "}
            {exchange.revision}
          </p>
        </div>
        {!closed ? (
          <Button
            variant="ghost"
            onClick={() => cancel.mutate()}
            disabled={cancel.isPending}
            data-testid="proposal-cancel-button"
          >
            <XCircle className="size-4" aria-hidden />
            Withdraw from deal
          </Button>
        ) : null}
      </header>

      <section className="bx-panel p-6">
        <CycleGraph cycle={toCycle(exchange)} />
      </section>

      <div className="grid gap-8 lg:grid-cols-12">
        <div className="space-y-8 lg:col-span-7">
          <section className="bx-panel space-y-4 p-6" data-testid="proposal-ledger">
            <h2 className="font-heading text-lg text-slate-900">Approval ledger</h2>
            <ul className="space-y-3">
              {exchange.participants.map((participant) => {
                const current =
                  participant.approval_status === "approved" &&
                  participant.approved_revision === exchange.revision;
                return (
                  <li
                    key={participant.id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
                    data-testid={`proposal-participant-${participant.user_id}`}
                  >
                    <div className="space-y-1">
                      <p className="font-medium text-slate-900">
                        {participant.user?.name ?? "Trader"}
                        {participant.user_id === user.id ? (
                          <span className="ml-2 font-mono text-[11px] text-blue-600">you</span>
                        ) : null}
                      </p>
                      {participant.user_id !== user.id ? (
                        <TraderBadge userId={participant.user_id} testId={`proposal-participant-${participant.user_id}-reputation`} />
                      ) : null}
                      <p className="text-xs text-slate-500">
                        gives {participant.gives_listing?.title} ({money(participant.value_given, participant.currency)}) ·
                        gets {participant.receives_listing?.title} ({money(participant.value_received, participant.currency)})
                      </p>
                      <p className="font-mono text-xs text-slate-500">
                        {balanceText(participant.balance_amount, participant.currency)}
                      </p>
                      {participant.changes_note ? (
                        <p className="text-xs text-amber-700">requested: {participant.changes_note}</p>
                      ) : null}
                    </div>
                    <div className="flex flex-col items-end gap-1.5 text-xs">
                      <span
                        className={`inline-flex items-center gap-1 ${current ? "text-green-600" : "text-slate-500"}`}
                        data-testid={`proposal-participant-${participant.user_id}-approval`}
                      >
                        {current ? <CheckCircle2 className="size-4 bx-pop" aria-hidden /> : <Clock className="size-4" aria-hidden />}
                        {current ? "approved" : "pending"}
                      </span>
                      <span
                        className={`inline-flex items-center gap-1 ${
                          participant.fulfilment_status === "confirmed" ? "text-green-600" : "text-slate-500"
                        }`}
                        data-testid={`proposal-participant-${participant.user_id}-fulfilment`}
                      >
                        <PackageCheck className="size-4" aria-hidden />
                        {participant.fulfilment_status === "confirmed" ? "fulfilled" : "not fulfilled"}
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>

            {me && !closed ? (
              <div className="space-y-4 border-t border-slate-200 pt-4">
                {exchange.allowed_actions.includes("approve") ? (
                  <Button
                    onClick={() => approve.mutate()}
                    disabled={approve.isPending || myApprovalCurrent}
                    data-testid="proposal-approve-button"
                  >
                    <CheckCircle2 className="size-4" aria-hidden />
                    {myApprovalCurrent ? `You approved revision ${exchange.revision}` : `Approve revision ${exchange.revision}`}
                  </Button>
                ) : null}
                <div className="space-y-2">
                  <Label htmlFor="proposal-change-note">Request a change</Label>
                  <Textarea
                    id="proposal-change-note"
                    rows={2}
                    value={changeNote}
                    onChange={(event) => setChangeNote(event.target.value)}
                    placeholder="e.g. include the camera strap and lens cap"
                    data-testid="proposal-change-note-textarea"
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => requestChanges.mutate()}
                    disabled={requestChanges.isPending || !changeNote.trim()}
                    data-testid="proposal-request-changes-button"
                  >
                    Request changes
                  </Button>
                  <p className="text-xs text-slate-500">
                    Changing a proposal starts a new revision and invalidates every earlier approval.
                  </p>
                </div>
              </div>
            ) : null}
          </section>

          <section className="bx-panel space-y-4 p-6" data-testid="proposal-history">
            <div className="flex items-center gap-2">
              <MessageSquare className="size-4 text-blue-600" aria-hidden />
              <h2 className="font-heading text-lg text-slate-900">Negotiation &amp; history</h2>
            </div>
            <ul className="space-y-2 text-sm">
              {[...approvals.map((approval) => ({
                id: approval.id,
                at: approval.created_at,
                text: `${exchange.participants.find((p) => p.user_id === approval.user_id)?.user?.name ?? "Trader"} ${
                  approval.decision === "approved" ? "approved" : "requested changes to"
                } revision ${approval.revision}${approval.note ? ` — “${approval.note}”` : ""}`,
              })),
              ...offers.map((offer) => ({
                id: offer.id,
                at: offer.created_at,
                text: `${offer.from_user_name}: ${offer.message}`,
              }))]
                .sort((a, b) => a.at.localeCompare(b.at))
                .map((entry) => (
                  <li key={entry.id} className="flex gap-3 text-slate-700" data-testid={`proposal-history-${entry.id}`}>
                    <span className="shrink-0 font-mono text-xs text-slate-500">{dateTime(entry.at)}</span>
                    <span>{entry.text}</span>
                  </li>
                ))}
              {approvals.length + offers.length === 0 ? (
                <li className="text-slate-500" data-testid="proposal-history-empty">No activity yet.</li>
              ) : null}
            </ul>
            {me && !closed && others.length ? (
              <form
                className="space-y-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  sendMessage.mutate(others[0].user_id);
                }}
              >
                <Textarea
                  rows={2}
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                  placeholder="Ask about pickup, timing, condition…"
                  data-testid="proposal-message-textarea"
                />
                <Button
                  type="submit"
                  size="sm"
                  variant="secondary"
                  disabled={sendMessage.isPending || !message.trim()}
                  data-testid="proposal-send-message-button"
                >
                  Send to participants
                </Button>
              </form>
            ) : null}
          </section>
        </div>

        <div className="space-y-8 lg:col-span-5">
          <section className="bx-panel space-y-4 p-6" data-testid="proposal-payment-panel">
            <div className="flex items-center gap-2">
              <Wallet className="size-4 text-blue-600" aria-hidden />
              <h2 className="font-heading text-lg text-slate-900">Balancing payment</h2>
            </div>
            <p className="text-sm text-slate-500" data-testid="proposal-payment-summary">
              {exchange.payment_summary.required === 0
                ? "This cycle is balanced — no money changes hands."
                : `${exchange.payment_summary.captured} of ${exchange.payment_summary.required} required payments verified (${money(
                    exchange.payment_summary.total_due,
                    exchange.payment_summary.currency,
                  )} due in total).`}
            </p>

            {me && owes ? (
              <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-sm text-slate-900">
                  You owe{" "}
                  <span className="font-mono text-amber-500" data-testid="proposal-my-balance">
                    {money(me.balance_amount, me.currency)}
                  </span>{" "}
                  because you receive more value than you give.
                </p>

                {myPayment?.verified ? (
                  <p className="inline-flex items-center gap-1.5 text-sm text-green-600" data-testid="proposal-payment-verified">
                    <CheckCircle2 className="size-4" aria-hidden />
                    Verified by PayPal ({myPayment.verification_source?.replace(/_/g, " ")})
                  </p>
                ) : !paymentPhase ? (
                  <p className="text-xs text-slate-500" data-testid="proposal-payment-locked">
                    Payment unlocks only after every participant approves the current revision.
                  </p>
                ) : paymentConfig.data && !paymentConfig.data.configured ? (
                  <p
                    className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700"
                    data-testid="proposal-payment-not-configured"
                  >
                    <ShieldAlert className="size-4 shrink-0" aria-hidden />
                    {paymentConfig.data.detail}
                  </p>
                ) : (
                  <>
                    <div className="flex items-start gap-2">
                      <Checkbox
                        id="proposal-authorise"
                        checked={authorised}
                        onCheckedChange={(value) => setAuthorised(Boolean(value))}
                        data-testid="proposal-authorise-checkbox"
                      />
                      <Label htmlFor="proposal-authorise" className="text-xs leading-relaxed text-slate-700">
                        I authorise a {money(me.balance_amount, me.currency)} balancing payment through PayPal
                        Sandbox for this exchange.
                      </Label>
                    </div>
                    <Button
                      className="w-full"
                      onClick={() => startPayment.mutate()}
                      disabled={!authorised || startPayment.isPending}
                      data-testid="proposal-paypal-pay-button"
                    >
                      {startPayment.isPending ? "Creating PayPal order…" : "Pay with PayPal Sandbox"}
                    </Button>
                    {myPayment && !myPayment.verified && myPayment.paypal_order_id ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full"
                        onClick={() => capture.mutate(myPayment.id)}
                        disabled={capture.isPending}
                        data-testid="proposal-paypal-verify-button"
                      >
                        {capture.isPending ? "Verifying with PayPal…" : "I approved on PayPal — verify now"}
                      </Button>
                    ) : null}
                    {myPayment?.last_error ? (
                      <p className="text-xs text-red-600" data-testid="proposal-payment-error">
                        {myPayment.last_error}
                      </p>
                    ) : null}
                  </>
                )}
              </div>
            ) : me ? (
              <p className="text-sm text-slate-500">
                {me.balance_amount < -0.005
                  ? `You are owed ${money(Math.abs(me.balance_amount), me.currency)} from the other participants.`
                  : "You don't owe a balancing payment on this exchange."}
              </p>
            ) : null}

            <p className="text-xs leading-relaxed text-slate-500" data-testid="proposal-escrow-note">
              {paymentConfig.data?.escrow_note ??
                "PayPal is not an escrow service. A payment only counts once PayPal confirms it server-side."}
            </p>
          </section>

          <ExchangeActions detail={detail.data!} viewerId={user.id} />

          <PayoutsPanel exchange={exchange} viewerId={user.id} />

          {exchange.status === "completed" ? (
            <section className="bx-panel space-y-5 p-6" data-testid="proposal-reviews-panel">
              <h2 className="font-heading text-lg text-slate-900">Review your trading partners</h2>
              {others.map((participant) => (
                <div key={participant.user_id} className="space-y-2">
                  <p className="text-sm text-slate-700">{participant.user?.name ?? "Trader"}</p>
                  <ReviewForm
                    subjectId={participant.user_id}
                    subjectName={participant.user?.name ?? "Trader"}
                    exchangeId={exchange.id}
                    testId={`proposal-review-${participant.user_id}`}
                  />
                </div>
              ))}
            </section>
          ) : null}

          <section className="bx-panel space-y-4 p-6" data-testid="proposal-fulfilment-panel">
            <div className="flex items-center gap-2">
              <PackageCheck className="size-4 text-green-600" aria-hidden />
              <h2 className="font-heading text-lg text-slate-900">Fulfilment</h2>
            </div>
            <p className="text-sm text-slate-500">
              Handing over the goods or delivering the service is tracked separately from payment. The exchange
              completes when every participant confirms they have received their side.
            </p>
            {me && !closed ? (
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => fulfil.mutate()}
                disabled={!canFulfil || fulfil.isPending || me.fulfilment_status === "confirmed"}
                data-testid="proposal-confirm-fulfilment-button"
              >
                {me.fulfilment_status === "confirmed"
                  ? "You confirmed fulfilment"
                  : canFulfil
                    ? "Confirm I received my side"
                    : "Available after approvals and payments"}
              </Button>
            ) : null}
            {exchange.status === "completed" ? (
              <p className="bx-pop inline-flex items-center gap-1.5 text-sm text-green-600" data-testid="proposal-completed">
                <CheckCircle2 className="size-4" aria-hidden />
                Exchange completed
              </p>
            ) : null}
          </section>

          <section className="bx-panel space-y-4 p-6" data-testid="proposal-ai-panel">
            <div className="flex items-center gap-2">
              <Sparkles className="size-4 text-fuchsia-300" aria-hidden />
              <h2 className="font-heading text-lg text-slate-900">AI deal summary</h2>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => dealSummary.mutate()}
              disabled={dealSummary.isPending}
              data-testid="proposal-deal-summary-button"
            >
              {dealSummary.isPending ? "Summarising…" : summary ? "Regenerate summary" : "Summarise this deal"}
            </Button>
            {dealSummary.isPending ? <div className="bx-shimmer h-20 rounded-xl border border-slate-200" /> : null}
            {summary ? (
              <div className="bx-pop space-y-3 text-sm" data-testid="proposal-deal-summary">
                <p className="leading-relaxed text-slate-900">{summary.summary}</p>
                {summary.open_questions.length ? (
                  <div>
                    <p className="font-mono text-[11px] uppercase tracking-wide text-slate-500">Open questions</p>
                    <ul className="mt-1.5 list-disc space-y-1 pl-5 text-slate-700">
                      {summary.open_questions.map((question) => (
                        <li key={question}>{question}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {summary.negotiation_suggestions.length ? (
                  <div>
                    <p className="font-mono text-[11px] uppercase tracking-wide text-slate-500">Negotiation ideas</p>
                    <ul className="mt-1.5 list-disc space-y-1 pl-5 text-slate-700">
                      {summary.negotiation_suggestions.map((suggestion) => (
                        <li key={suggestion}>{suggestion}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                <p className="text-xs text-slate-500">{summary.disclaimer}</p>
              </div>
            ) : (
              <p className="text-xs text-slate-500">
                Advisory only — the AI cannot approve, accept offers or authorise a payment.
              </p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
