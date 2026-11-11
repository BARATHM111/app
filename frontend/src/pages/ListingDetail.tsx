import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, MapPin, Repeat2, Tag } from "lucide-react";

import { CategoryChip, StatusBadge, TypeBadge } from "@/components/Badges";
import { apiGet } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import type { Listing } from "@/lib/types";
import TraderBadge from "@/components/TraderBadge";

export default function ListingDetail() {
  const { id = "" } = useParams();
  const listing = useQuery({
    queryKey: ["listing", id],
    queryFn: () => apiGet<Listing>(`/v1/listings/${id}`),
    retry: false,
  });

  return (
    <div className="space-y-8">
      <Link
        to="/marketplace"
        className="inline-flex items-center gap-2 text-sm text-slate-500 transition-colors duration-200 hover:text-slate-900"
        data-testid="listing-detail-back-link"
      >
        <ArrowLeft className="size-4" aria-hidden />
        Back to marketplace
      </Link>

      {listing.isLoading ? (
        <div className="h-64 rounded-2xl border border-slate-200 bg-white bx-shimmer" />
      ) : null}

      {listing.isError ? (
        <div className="bx-panel p-8" data-testid="listing-detail-error">
          <h1 className="font-heading text-xl text-slate-900">This listing isn't available</h1>
          <p className="mt-2 text-sm text-slate-500">
            It may have been traded away, taken off the market, or the link is wrong.
          </p>
        </div>
      ) : null}

      {listing.data ? (
        <div className="grid gap-8 lg:grid-cols-12">
          <article className="bx-panel space-y-6 p-6 lg:col-span-8 sm:p-8">
            <div className="flex flex-wrap items-center gap-2">
              <TypeBadge type={listing.data.type} testId="listing-detail-type-badge" />
              <CategoryChip category={listing.data.category} />
              <StatusBadge status={listing.data.status} />
            </div>
            <h1 className="font-heading text-3xl font-semibold text-slate-900" data-testid="listing-detail-title">
              {listing.data.title}
            </h1>
            <p className="whitespace-pre-line text-slate-700">{listing.data.description}</p>

            <dl className="grid gap-4 sm:grid-cols-3">
              <Field label="Estimated barter value">
                <span className="font-mono text-blue-600" data-testid="listing-detail-value">
                  {money(listing.data.estimated_value, listing.data.currency)}
                </span>
              </Field>
              <Field label="Condition">{listing.data.condition || "Not stated"}</Field>
              <Field label="Listed">{shortDate(listing.data.created_at)}</Field>
            </dl>

            {listing.data.tags.length ? (
              <div className="flex flex-wrap gap-2">
                {listing.data.tags.map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-700"
                  >
                    <Tag className="size-3" aria-hidden />
                    {tag}
                  </span>
                ))}
              </div>
            ) : null}

            {listing.data.ai_assisted ? (
              <p className="rounded-xl border border-fuchsia-500/25 bg-fuchsia-500/5 p-3 text-xs text-fuchsia-200">
                Fields on this listing were drafted by AI and reviewed by the trader before publishing.
              </p>
            ) : null}
          </article>

          <aside className="space-y-6 lg:col-span-4">
            <div className="bx-panel space-y-3 p-6">
              <p className="font-mono text-[11px] uppercase tracking-wide text-slate-500">Offered by</p>
              <Link
                to={`/trader/${listing.data.owner_id}`}
                className="block font-heading text-lg text-slate-900 transition-colors duration-200 hover:text-blue-700"
                data-testid="listing-detail-owner"
              >
                {listing.data.owner?.name ?? "Trader"}
              </Link>
              <TraderBadge userId={listing.data.owner_id} testId="listing-detail-owner-reputation" />
              {listing.data.owner?.location ? (
                <p className="inline-flex items-center gap-1.5 text-sm text-slate-500">
                  <MapPin className="size-4" aria-hidden />
                  {listing.data.owner.location}
                </p>
              ) : null}
            </div>

            <div className="bx-panel space-y-4 p-6">
              <h2 className="font-heading text-lg text-slate-900">Want to trade for this?</h2>
              <p className="text-sm leading-relaxed text-slate-500">
                Post a want that names what you are offering in return. Once your want and their listing sit
                in the same loop, the graph engine can build a cycle.
              </p>
              <Link
                to="/wants"
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-blue-600"
                data-testid="listing-detail-create-want-link"
              >
                <Repeat2 className="size-4" aria-hidden />
                Create a want
              </Link>
              <Link
                to="/cycles"
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm text-slate-900 transition-colors duration-200 hover:bg-slate-100"
                data-testid="listing-detail-view-cycles-link"
              >
                Look for a cycle
              </Link>
            </div>

            <p className="text-xs leading-relaxed text-slate-500">
              Estimated values are the trader's own estimates, not verified valuations. BarterX never
              guarantees that a suggested trade will complete.
            </p>
          </aside>
        </div>
      ) : null}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
      <dt className="text-[11px] uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm text-slate-900">{children}</dd>
    </div>
  );
}
