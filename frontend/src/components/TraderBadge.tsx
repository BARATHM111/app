import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, Star } from "lucide-react";

import { apiGet } from "@/lib/api";
import type { Reputation } from "@/lib/types";

export function reputationQuery(userId: string) {
  return {
    queryKey: ["reputation", userId],
    queryFn: () => apiGet<Reputation>(`/v1/users/${userId}/reputation`),
    staleTime: 60_000,
  };
}

/** Compact trust signal: completed trades plus the average of verified reviews. Links to the trader page. */
export default function TraderBadge({ userId, testId }: { userId: string; testId: string }) {
  const reputation = useQuery(reputationQuery(userId));
  const data = reputation.data;

  return (
    <Link
      to={`/trader/${userId}`}
      className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] text-slate-700 transition-colors duration-200 hover:border-blue-300 hover:text-blue-700"
      data-testid={testId}
    >
      {reputation.isLoading ? (
        <span className="bx-shimmer h-3 w-16 rounded" />
      ) : data ? (
        <>
          <span className="inline-flex items-center gap-1" data-testid={`${testId}-trades`}>
            <BadgeCheck className="size-3 text-green-600" aria-hidden />
            {data.completed_trades} {data.completed_trades === 1 ? "trade" : "trades"}
          </span>
          <span className="inline-flex items-center gap-1" data-testid={`${testId}-rating`}>
            <Star className="size-3 text-amber-500" aria-hidden />
            {data.average_rating != null ? `${data.average_rating.toFixed(1)} (${data.verified_review_count})` : "no verified reviews"}
          </span>
        </>
      ) : (
        <span>View trader</span>
      )}
    </Link>
  );
}
