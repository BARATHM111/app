import { Link } from "react-router-dom";
import { ArrowUpRight, MapPin } from "lucide-react";

import { CategoryChip, StatusBadge, TypeBadge } from "@/components/Badges";
import { money } from "@/lib/format";
import type { Listing } from "@/lib/types";

export default function ListingCard({ listing, featured = false }: { listing: Listing; featured?: boolean }) {
  return (
    <article
      className={`bx-node flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-6 backdrop-blur-xl ${
        featured ? "sm:p-8" : ""
      }`}
      data-testid={`listing-card-${listing.id}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <TypeBadge type={listing.type} testId={`listing-card-${listing.id}-type-badge`} />
        <CategoryChip category={listing.category} />
        {listing.status !== "active" ? <StatusBadge status={listing.status} /> : null}
      </div>

      <div className="space-y-2">
        <h3 className={`font-heading font-semibold text-slate-900 ${featured ? "text-2xl" : "text-xl"}`}>
          {listing.title}
        </h3>
        <p className="line-clamp-3 text-sm leading-relaxed text-slate-500">{listing.description}</p>
      </div>

      <div className="flex items-end justify-between gap-4">
        <div>
          <p
            className={`font-mono text-blue-600 ${featured ? "text-2xl" : "text-lg"}`}
            data-testid={`listing-card-${listing.id}-value`}
          >
            {money(listing.estimated_value, listing.currency)}
          </p>
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Estimated barter value</p>
        </div>
        <div className="text-right text-xs text-slate-500">
          <p data-testid={`listing-card-${listing.id}-owner`}>{listing.owner?.name ?? "Trader"}</p>
          {listing.owner?.location ? (
            <p className="inline-flex items-center gap-1 text-slate-500">
              <MapPin className="size-3" aria-hidden />
              {listing.owner.location}
            </p>
          ) : null}
        </div>
      </div>

      {listing.tags.length ? (
        <div className="flex flex-wrap gap-1.5">
          {listing.tags.slice(0, featured ? 6 : 4).map((tag) => (
            <span key={tag} className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500">
              #{tag}
            </span>
          ))}
        </div>
      ) : null}

      <Link
        to={`/listing/${listing.id}`}
        className="mt-auto inline-flex items-center gap-1 text-sm font-medium text-blue-600 transition-colors duration-200 hover:text-blue-700"
        data-testid={`listing-card-${listing.id}-view-link`}
      >
        View listing
        <ArrowUpRight className="size-4" aria-hidden />
      </Link>
    </article>
  );
}
