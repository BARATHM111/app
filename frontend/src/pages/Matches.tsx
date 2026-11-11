import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import MatchCard from "@/components/MatchCard";
import { apiGet } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { MatchPage } from "@/lib/types";

export default function Matches() {
  const { user, isLoading } = useSession();
  const matches = useQuery({
    queryKey: ["matches"],
    queryFn: async () => (await apiGet<MatchPage>("/v1/matches")).items,
    enabled: Boolean(user),
    retry: false,
  });

  if (isLoading) {
    return <div className="h-64 rounded-2xl border border-slate-200 bg-white bx-shimmer" />;
  }

  if (!user) {
    return (
      <div className="bx-panel mx-auto max-w-xl space-y-4 p-8 text-center" data-testid="matches-signin-prompt">
        <h1 className="font-heading text-2xl text-slate-900">Sign in to see your matches</h1>
        <p className="text-sm text-slate-500">
          Matches are built from your own wants and the listing you offer in return.
        </p>
        <Link
          to="/login"
          className="inline-flex rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-blue-600"
          data-testid="matches-signin-link"
        >
          Sign in
        </Link>
      </div>
    );
  }

  const items = matches.data ?? [];

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <h1 className="font-heading text-3xl font-semibold text-slate-900">Semantic matches</h1>
        <p className="max-w-3xl text-slate-500">
          Embeddings rank listings whose text reads like what you asked for; deterministic rules then check
          type, category, currency and the value range before anything reaches this list. These are
          candidates, never guaranteed exchanges.
        </p>
      </div>

      {matches.isError ? (
        <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700" data-testid="matches-error">
          Matches could not be computed right now — nothing is broken, try again shortly.
        </p>
      ) : null}

      {!matches.isLoading && items.length === 0 ? (
        <div className="bx-panel space-y-3 p-8" data-testid="matches-empty-state">
          <h2 className="font-heading text-lg text-slate-900">No compatible candidates yet</h2>
          <p className="text-sm text-slate-500">
            Matching needs two things: a want that describes what you are after, and one of your own active
            listings offered in return. Listings already committed to another proposal are excluded.
          </p>
          <div className="flex flex-wrap gap-3 pt-1">
            <Link
              to="/wants"
              className="rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-blue-600"
              data-testid="matches-create-want-link"
            >
              Refine my wants
            </Link>
            <Link
              to="/marketplace"
              className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm text-slate-900 transition-colors duration-200 hover:bg-slate-100"
              data-testid="matches-browse-link"
            >
              Browse the marketplace
            </Link>
          </div>
        </div>
      ) : null}

      <section className="space-y-6" data-testid="matches-list">
        {items.map((match) => (
          <MatchCard key={match.id} match={match} />
        ))}
      </section>
    </div>
  );
}
