import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles, X } from "lucide-react";
import { toast } from "sonner";

import { CategoryChip, TypeBadge } from "@/components/Badges";
import { Button } from "@/components/ui/button";
import { apiPost } from "@/lib/api";
import { extractErrorMessage, money, percent } from "@/lib/format";
import type { Match, MatchExplanationResponse, MessageResponse } from "@/lib/types";

export default function MatchCard({ match }: { match: Match }) {
  const queryClient = useQueryClient();

  const explain = useMutation({
    mutationFn: () =>
      apiPost<MatchExplanationResponse>("/v1/ai/explain-match", { match_id: match.id }),
    onSuccess: (data) => {
      queryClient.setQueryData<Match[]>(["matches"], (current) =>
        (current ?? []).map((item) =>
          item.id === match.id
            ? { ...item, explanation: data.explanation, explanation_generated_at: data.generated_at }
            : item,
        ),
      );
      toast.success(data.cached ? "Explanation loaded" : "Explanation generated");
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not generate an explanation")),
  });

  const dismiss = useMutation({
    mutationFn: () => apiPost<MessageResponse>(`/v1/matches/${match.id}/dismiss`),
    onSuccess: () => {
      queryClient.setQueryData<Match[]>(["matches"], (current) =>
        (current ?? []).filter((item) => item.id !== match.id),
      );
      toast.success("Match dismissed");
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not dismiss this match")),
  });

  const listing = match.candidate_listing;
  if (!listing) return null;

  return (
    <article
      className="bx-node rounded-2xl border border-slate-200 bg-white p-6 backdrop-blur-xl"
      data-testid={`match-card-${match.id}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <TypeBadge type={listing.type} testId={`match-card-${match.id}-type-badge`} />
            <CategoryChip category={listing.category} />
            <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-blue-600">
              score {percent(match.score)}
            </span>
          </div>
          <h3 className="font-heading text-lg font-semibold text-slate-900" data-testid={`match-card-${match.id}-title`}>
            {listing.title}
          </h3>
          <p className="text-sm text-slate-500">
            {money(listing.estimated_value, listing.currency)} · offered by{" "}
            {match.offered_listing ? `you: ${match.offered_listing.title}` : "another trader"}
          </p>
        </div>

        <div className="flex gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => explain.mutate()}
            disabled={explain.isPending}
            data-testid={`match-card-${match.id}-explain-button`}
          >
            <Sparkles className="size-4" aria-hidden />
            {explain.isPending ? "Thinking…" : match.explanation ? "Refresh explanation" : "Explain with AI"}
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Dismiss match"
            onClick={() => dismiss.mutate()}
            disabled={dismiss.isPending}
            data-testid={`match-card-${match.id}-dismiss-button`}
          >
            <X className="size-4" aria-hidden />
          </Button>
        </div>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-12">
        <ul className="space-y-1.5 lg:col-span-7" data-testid={`match-card-${match.id}-reasons`}>
          {match.reasons.map((reason) => (
            <li key={reason} className="flex gap-2 text-sm text-slate-700">
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-blue-600" />
              {reason}
            </li>
          ))}
        </ul>

        <div className="space-y-3 lg:col-span-5">
          <div className="grid grid-cols-2 gap-3">
            <Meter label="Semantic · 45%" value={match.semantic_score} />
            <Meter label="Category · 25%" value={match.category_score} />
            <Meter label="Value · 20%" value={match.value_score} />
            <Meter label="Location · 10%" value={match.location_score} />
          </div>
          {match.explanation ? (
            <p
              className="bx-pop rounded-xl border border-blue-300 bg-blue-50 p-3 text-sm leading-relaxed text-slate-900"
              data-testid={`match-card-${match.id}-explanation`}
            >
              {match.explanation}
            </p>
          ) : (
            <p className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">
              AI explanations are advisory and unverified — ask for one when you want the reasoning in words.
            </p>
          )}
          <Link
            to={`/listing/${listing.id}`}
            className="inline-flex text-sm font-medium text-blue-600 transition-colors duration-200 hover:text-blue-700"
            data-testid={`match-card-${match.id}-view-listing-link`}
          >
            Open listing →
          </Link>
        </div>
      </div>
    </article>
  );
}

function Meter({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-blue-600"
          style={{ width: `${Math.max(4, Math.round(value * 100))}%` }}
        />
      </div>
      <p className="mt-1 font-mono text-xs text-slate-500">{value.toFixed(2)}</p>
    </div>
  );
}
