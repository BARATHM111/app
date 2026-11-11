import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitBranch, Info, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { CycleSizeBadge } from "@/components/Badges";
import CycleGraph from "@/components/CycleGraph";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiGet, apiPost } from "@/lib/api";
import { balanceText, extractErrorMessage, money, percent } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { CycleListResponse, ExchangeDetail, GraphStats } from "@/lib/types";
import TraderBadge from "@/components/TraderBadge";

export default function Cycles() {
  const { user, isLoading } = useSession();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [size, setSize] = useState("all");

  const cycles = useQuery({
    queryKey: ["cycles", size],
    queryFn: () =>
      apiGet<CycleListResponse>(
        `/v1/cycles?max_nodes=${size === "2" ? 2 : 3}&limit=30`,
      ),
    retry: false,
  });

  const stats = useQuery({
    queryKey: ["graph-stats"],
    queryFn: () => apiGet<GraphStats>("/v1/graph/stats"),
    retry: false,
  });

  const propose = useMutation({
    mutationFn: (payload: { cycle_key: string; participant_ids: string[] }) =>
      apiPost<ExchangeDetail>("/v1/exchanges/from-cycle", payload),
    onSuccess: async (detail) => {
      await queryClient.invalidateQueries({ queryKey: ["exchanges"] });
      await queryClient.invalidateQueries({ queryKey: ["listings"] });
      await queryClient.invalidateQueries({ queryKey: ["graph-stats"] });
      toast.success("Proposal created — every participant must now approve");
      navigate(`/proposal/${detail.exchange.id}`);
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not create that proposal")),
  });

  const all = cycles.data?.cycles ?? [];
  const visible = size === "all" ? all : all.filter((cycle) => String(cycle.cycle_type) === size);

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-2 rounded-full border border-green-200 bg-green-50 px-3 py-1 font-mono text-xs uppercase tracking-wide text-green-600">
            Deterministic graph engine
          </span>
          {stats.data ? (
            <span className="font-mono text-xs text-slate-500">
              {stats.data.nodes} traders · {stats.data.edges} trade edges · {stats.data.two_cycles} two-party ·{" "}
              {stats.data.three_cycles} three-party
            </span>
          ) : null}
        </div>
        <h1 className="font-heading text-3xl font-semibold text-slate-900">Discovered cycles</h1>
        <p className="max-w-3xl text-slate-500">
          A cycle exists when every trader gives something the next trader wants, all the way around.
          Values, balances and the cycle itself are computed in code — no AI decides whether a trade is
          valid. Each cycle is a candidate: nothing is committed until every participant approves.
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <Tabs value={size} onValueChange={(value: string) => setSize(value)}>
          <TabsList data-testid="cycles-size-tabs">
            <TabsTrigger value="all" data-testid="cycles-tab-all">
              All cycles
            </TabsTrigger>
            <TabsTrigger value="2" data-testid="cycles-tab-two">
              Two-party
            </TabsTrigger>
            <TabsTrigger value="3" data-testid="cycles-tab-three">
              Three-party
            </TabsTrigger>
          </TabsList>
        </Tabs>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            queryClient.invalidateQueries({ queryKey: ["cycles"] });
            queryClient.invalidateQueries({ queryKey: ["graph-stats"] });
          }}
          data-testid="cycles-recompute-button"
        >
          <RefreshCw className="size-4" aria-hidden />
          Recompute
        </Button>
      </div>

      {cycles.isError ? (
        <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700" data-testid="cycles-error">
          Cycles could not be computed right now. Nothing was changed — try again in a moment.
        </p>
      ) : null}

      {cycles.isLoading ? (
        <div className="h-72 rounded-2xl border border-slate-200 bg-white bx-shimmer" data-testid="cycles-loading" />
      ) : null}

      {!cycles.isLoading && visible.length === 0 ? (
        <div className="bx-panel space-y-3 p-8" data-testid="cycles-empty-state">
          <h2 className="font-heading text-lg text-slate-900">No complete loops right now</h2>
          <p className="text-sm text-slate-500">
            A loop needs at least two traders whose listings satisfy each other's wants. Add a want with an
            offering attached, or list something someone else is already asking for. Listings committed to a
            live proposal are held back and cannot be double-booked.
          </p>
          <div className="flex flex-wrap gap-3 pt-1">
            <Link
              to="/wants"
              className="rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-blue-600"
              data-testid="cycles-manage-wants-link"
            >
              Manage my wants
            </Link>
            <Link
              to="/marketplace"
              className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm text-slate-900 transition-colors duration-200 hover:bg-slate-100"
              data-testid="cycles-browse-link"
            >
              Browse listings
            </Link>
          </div>
        </div>
      ) : null}

      <section className="space-y-8" data-testid="cycles-list">
        {visible.map((cycle) => (
          <article
            key={cycle.key}
            className="bx-panel space-y-6 p-6 sm:p-8"
            data-testid={`cycle-card-${cycle.key}`}
          >
            <header className="flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="rounded-md bg-blue-600 px-2 py-0.5 font-mono text-[11px] font-semibold text-white" data-testid={`cycle-card-${cycle.key}-rank`}>
                    #{cycle.rank}
                  </span>
                  <CycleSizeBadge size={cycle.cycle_type} />
                </div>
                <h2 className="font-heading text-xl font-semibold text-slate-900">
                  {cycle.participants.map((participant) => participant.user_name).join(" → ")} →{" "}
                  {cycle.participants[0]?.user_name}
                </h2>
                <p className="font-mono text-xs text-slate-500">
                  {money(cycle.total_value, cycle.participants[0]?.currency ?? "USD")} crossing the loop ·
                  value differences {money(cycle.total_imbalance, cycle.participants[0]?.currency ?? "USD")} · weakest
                  link {percent(cycle.min_edge_score)} · average {percent(cycle.avg_edge_score)}
                </p>
                <ul className="list-disc space-y-0.5 pl-4 text-xs text-slate-500" data-testid={`cycle-card-${cycle.key}-reasons`}>
                  {cycle.reasons.slice(0, 3).map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>
              {user ? (
                <Button
                  onClick={() =>
                    propose.mutate({ cycle_key: cycle.key, participant_ids: cycle.participant_ids })
                  }
                  disabled={propose.isPending || !cycle.participant_ids.includes(user.id)}
                  data-testid={`cycle-card-${cycle.key}-propose-button`}
                >
                  <GitBranch className="size-4" aria-hidden />
                  {cycle.participant_ids.includes(user.id)
                    ? propose.isPending
                      ? "Creating proposal…"
                      : "Propose this exchange"
                    : "You're not in this cycle"}
                </Button>
              ) : (
                <Link
                  to="/login"
                  className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm text-slate-900 transition-colors duration-200 hover:bg-slate-100"
                  data-testid={`cycle-card-${cycle.key}-signin-link`}
                >
                  Sign in to propose
                </Link>
              )}
            </header>

            <CycleGraph cycle={cycle} />

            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-[11px] uppercase tracking-wide text-slate-500">
                    <th className="pb-2 pr-4">Trader</th>
                    <th className="pb-2 pr-4">Gives</th>
                    <th className="pb-2 pr-4">Receives</th>
                    <th className="pb-2 text-right">Balancing payment</th>
                  </tr>
                </thead>
                <tbody>
                  {cycle.participants.map((participant) => (
                    <tr
                      key={participant.user_id}
                      className="border-b border-slate-200 last:border-0"
                      data-testid={`cycle-card-${cycle.key}-row-${participant.user_id}`}
                    >
                      <td className="py-2.5 pr-4 text-slate-900">
                        <div className="flex flex-col items-start gap-1">
                          <span>{participant.user_name}</span>
                          <TraderBadge
                            userId={participant.user_id}
                            testId={`cycle-card-${cycle.key}-row-${participant.user_id}-reputation`}
                          />
                        </div>
                      </td>
                      <td className="py-2.5 pr-4 text-slate-700">
                        {participant.gives_listing_title}
                        <span className="ml-2 font-mono text-xs text-slate-500">
                          {money(participant.gives_value, participant.currency)}
                        </span>
                      </td>
                      <td className="py-2.5 pr-4 text-slate-700">
                        {participant.receives_listing_title}
                        <span className="ml-2 font-mono text-xs text-slate-500">
                          {money(participant.receives_value, participant.currency)}
                        </span>
                      </td>
                      <td className="py-2.5 text-right font-mono text-xs">
                        <span
                          className={
                            participant.balance_amount > 0
                              ? "text-amber-500"
                              : participant.balance_amount < 0
                                ? "text-blue-600"
                                : "text-green-600"
                          }
                        >
                          {balanceText(participant.balance_amount, participant.currency)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="flex gap-2 text-xs leading-relaxed text-slate-500">
              <Info className="mt-0.5 size-4 shrink-0 text-slate-500" aria-hidden />
              {stats.data?.note ??
                "Candidate cycle — every participant must approve before anything is reserved."}
            </p>
          </article>
        ))}
      </section>

      {isLoading ? <div className="h-24 bx-shimmer rounded-2xl" /> : null}
    </div>
  );
}
