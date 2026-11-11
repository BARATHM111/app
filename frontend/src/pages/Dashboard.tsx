import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, GitBranch, ListChecks, Package, Sparkles, Wallet } from "lucide-react";

import { StatusBadge, TypeBadge } from "@/components/Badges";
import { apiGet } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import { useSession } from "@/lib/session";
import PayoutSettings from "@/components/PayoutSettings";
import TraderBadge from "@/components/TraderBadge";
import type {
  ExchangeListResponse,
  ListingPage,
  MatchPage,
  WantListResponse,
} from "@/lib/types";

export default function Dashboard() {
  const { user, isLoading } = useSession();

  const listings = useQuery({
    queryKey: ["my-listings"],
    queryFn: () => apiGet<ListingPage>("/v1/listings/mine?page_size=50"),
    enabled: Boolean(user),
    retry: false,
  });

  const wants = useQuery({
    queryKey: ["wants"],
    queryFn: () => apiGet<WantListResponse>("/v1/wants"),
    enabled: Boolean(user),
    retry: false,
  });

  const matches = useQuery({
    queryKey: ["matches"],
    queryFn: async () => (await apiGet<MatchPage>("/v1/matches")).items,
    enabled: Boolean(user),
    retry: false,
  });

  const exchanges = useQuery({
    queryKey: ["exchanges"],
    queryFn: () => apiGet<ExchangeListResponse>("/v1/exchanges"),
    enabled: Boolean(user),
    retry: false,
  });

  if (isLoading) {
    return <div className="h-64 rounded-2xl border border-slate-200 bg-white bx-shimmer" />;
  }

  if (!user) {
    return (
      <div className="bx-panel mx-auto max-w-xl space-y-4 p-8 text-center" data-testid="dashboard-signin-prompt">
        <h1 className="font-heading text-2xl text-slate-900">Your trading desk</h1>
        <p className="text-sm text-slate-500">
          Sign in to see your listings, wants, matches and live proposals.
        </p>
        <Link
          to="/login"
          className="inline-flex rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-blue-600"
          data-testid="dashboard-signin-link"
        >
          Sign in
        </Link>
      </div>
    );
  }

  const myListings = listings.data?.items ?? [];
  const activeListings = myListings.filter((listing) => listing.status === "active").length;
  const myWants = wants.data?.wants ?? [];
  const liveExchanges = (exchanges.data?.exchanges ?? []).filter(
    (exchange) => exchange.status !== "completed" && exchange.status !== "cancelled",
  );

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="font-heading text-3xl font-semibold text-slate-900">Your trading desk</h1>
        <p className="text-slate-500" data-testid="dashboard-owner-name">
          Signed in as {user.name} · every value here is an estimate, every approval is explicit.
        </p>
      </div>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tile
          icon={Package}
          label="Active listings"
          value={String(activeListings)}
          hint={`${myListings.length} total`}
          to="/marketplace"
          testId="dashboard-tile-listings"
        />
        <Tile
          icon={ListChecks}
          label="Open wants"
          value={String(myWants.filter((want) => want.status === "open").length)}
          hint={`${myWants.filter((want) => want.listing_id).length} with an offering attached`}
          to="/wants"
          testId="dashboard-tile-wants"
        />
        <Tile
          icon={Sparkles}
          label="Semantic matches"
          value={String(matches.data?.length ?? 0)}
          hint="Candidates, not commitments"
          to="/matches"
          testId="dashboard-tile-matches"
        />
        <Tile
          icon={GitBranch}
          label="Live proposals"
          value={String(liveExchanges.length)}
          hint="Needing attention or approval"
          to="/cycles"
          testId="dashboard-tile-exchanges"
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <PayoutSettings user={user} />
        </div>
        <div className="bx-panel flex flex-col justify-between gap-3 p-6 lg:col-span-4" data-testid="dashboard-reputation-card">
          <span className="font-heading text-lg text-slate-900">Your reputation</span>
          <TraderBadge userId={user.id} testId="dashboard-reputation" />
          <Link to={`/trader/${user.id}`} className="text-xs font-medium text-blue-600 hover:text-blue-700" data-testid="dashboard-reputation-link">
            See what trading partners say about you →
          </Link>
        </div>
      </section>

      <section className="grid gap-8 lg:grid-cols-12">
        <div className="bx-panel space-y-4 p-6 lg:col-span-7">
          <div className="flex items-center justify-between gap-4">
            <h2 className="font-heading text-lg text-slate-900">My listings</h2>
            <Link
              to="/create-listing"
              className="text-sm font-medium text-blue-600 transition-colors duration-200 hover:text-blue-700"
              data-testid="dashboard-create-listing-link"
            >
              Add a listing →
            </Link>
          </div>
          {listings.isError ? (
            <p className="text-sm text-amber-700" data-testid="dashboard-listings-error">
              Listings could not be loaded right now.
            </p>
          ) : null}
          {!listings.isLoading && myListings.length === 0 ? (
            <p className="text-sm text-slate-500" data-testid="dashboard-listings-empty">
              Nothing listed yet. Describe something you would happily trade away.
            </p>
          ) : null}
          <ul className="space-y-3" data-testid="dashboard-listings">
            {myListings.map((listing) => (
              <li
                key={listing.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
              >
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <TypeBadge type={listing.type} testId={`dashboard-listing-${listing.id}-type-badge`} />
                    <StatusBadge status={listing.status} />
                  </div>
                  <Link
                    to={`/listing/${listing.id}`}
                    className="font-medium text-slate-900 transition-colors duration-200 hover:text-blue-700"
                    data-testid={`dashboard-listing-${listing.id}-link`}
                  >
                    {listing.title}
                  </Link>
                </div>
                <div className="text-right">
                  <p className="font-mono text-sm text-blue-600">
                    {money(listing.estimated_value, listing.currency)}
                  </p>
                  {listing.in_active_exchange ? (
                    <p className="font-mono text-[11px] text-amber-500">committed to an exchange</p>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="space-y-8 lg:col-span-5">
          <div className="bx-panel space-y-4 p-6">
            <h2 className="font-heading text-lg text-slate-900">Live proposals</h2>
            {exchanges.isError ? (
              <p className="text-sm text-amber-700" data-testid="dashboard-exchanges-error">
                Proposals could not be loaded right now.
              </p>
            ) : null}
            {!exchanges.isLoading && liveExchanges.length === 0 ? (
              <p className="text-sm text-slate-500" data-testid="dashboard-exchanges-empty">
                No open proposals. Head to the cycles page to find a loop worth proposing.
              </p>
            ) : null}
            <ul className="space-y-3" data-testid="dashboard-exchanges">
              {liveExchanges.map((exchange) => (
                <li key={exchange.id}>
                  <Link
                    to={`/proposal/${exchange.id}`}
                    className="bx-node block rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
                    data-testid={`dashboard-exchange-${exchange.id}-link`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <StatusBadge status={exchange.status} />
                      <span className="font-mono text-xs text-slate-500">
                        rev {exchange.revision} · {money(exchange.total_value, exchange.currency)}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-slate-700">
                      {exchange.cycle_type}-party cycle with{" "}
                      {exchange.counterparties.map((party) => party.name).join(", ") || "other traders"}
                    </p>
                    {exchange.my_role ? (
                      <p className="mt-1 font-mono text-[11px] text-slate-500">
                        your side: {exchange.my_role === "payer" ? "owes a balancing payment" : "receives value"}
                      </p>
                    ) : null}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          <div className="bx-panel space-y-3 p-6">
            <div className="flex items-center gap-2">
              <Wallet className="size-4 text-blue-600" aria-hidden />
              <h2 className="font-heading text-lg text-slate-900">Your wants</h2>
            </div>
            <ul className="space-y-2" data-testid="dashboard-wants">
              {myWants.slice(0, 5).map((want) => (
                <li key={want.id} className="flex items-center justify-between gap-3 text-sm">
                  <span className="truncate text-slate-700">{want.title}</span>
                  <span className="shrink-0 font-mono text-xs text-slate-500">
                    {want.listing_id ? "offering attached" : "no offering"}
                  </span>
                </li>
              ))}
            </ul>
            <Link
              to="/wants"
              className="inline-flex items-center gap-1 text-sm font-medium text-blue-600 transition-colors duration-200 hover:text-blue-700"
              data-testid="dashboard-manage-wants-link"
            >
              Manage wants
              <ArrowRight className="size-4" aria-hidden />
            </Link>
          </div>

          <p className="font-mono text-[11px] text-slate-500">
            member since {shortDate(user.created_at)}
          </p>
        </div>
      </section>
    </div>
  );
}

function Tile({
  icon: Icon,
  label,
  value,
  hint,
  to,
  testId,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  hint: string;
  to: string;
  testId: string;
}) {
  return (
    <Link
      to={to}
      className="bx-node rounded-2xl border border-slate-200 bg-white p-5 backdrop-blur-xl"
      data-testid={testId}
    >
      <div className="flex items-center gap-3">
        <span className="grid size-9 place-items-center rounded-lg bg-slate-100 text-blue-600">
          <Icon className="size-4" />
        </span>
        <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      </div>
      <p className="mt-3 font-mono text-3xl text-slate-900">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{hint}</p>
    </Link>
  );
}
