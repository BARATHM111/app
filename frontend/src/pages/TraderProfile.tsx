import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BadgeCheck, MapPin, Star } from "lucide-react";

import ReviewForm from "@/components/ReviewForm";
import { reputationQuery } from "@/components/TraderBadge";
import { apiGet } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { ListingBrief, UserPublic } from "@/lib/types";

function Stars({ rating }: { rating: number }) {
  return (
    <span className="inline-flex" aria-label={`${rating} out of 5`}>
      {[1, 2, 3, 4, 5].map((value) => (
        <Star key={value} className={`size-3.5 ${value <= rating ? "fill-amber-300 text-amber-500" : "text-slate-700"}`} aria-hidden />
      ))}
    </span>
  );
}

export default function TraderProfile() {
  const { id = "" } = useParams();
  const { user } = useSession();
  const profile = useQuery({ queryKey: ["trader", id], queryFn: () => apiGet<UserPublic>(`/v1/users/${id}`) });
  const reputation = useQuery({ ...reputationQuery(id), queryKey: ["reputation", id, user?.id ?? "anon"] });
  const listings = useQuery({ queryKey: ["trader-listings", id], queryFn: () => apiGet<ListingBrief[]>(`/v1/users/${id}/listings`) });

  const rep = reputation.data;
  const isSelf = user?.id === id;

  return (
    <div className="space-y-8">
      <Link
        to="/marketplace"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 transition-colors duration-200 hover:text-slate-900"
        data-testid="trader-back-link"
      >
        <ArrowLeft className="size-4" aria-hidden /> Marketplace
      </Link>

      <section className="bx-panel grid gap-6 p-6 sm:p-8 lg:grid-cols-12">
        <div className="space-y-2 lg:col-span-7">
          {profile.isError ? (
            <p className="text-amber-700" data-testid="trader-not-found">
              This trader could not be found.
            </p>
          ) : (
            <>
              <h1 className="font-heading text-3xl text-slate-900" data-testid="trader-name">
                {profile.data?.name ?? rep?.name ?? "Trader"}
              </h1>
              {profile.data?.location ? (
                <p className="flex items-center gap-1.5 text-sm text-slate-500" data-testid="trader-location">
                  <MapPin className="size-4" aria-hidden /> {profile.data.location}
                </p>
              ) : null}
              {profile.data?.bio ? <p className="max-w-prose text-sm text-slate-700" data-testid="trader-bio">{profile.data.bio}</p> : null}
            </>
          )}
        </div>
        <dl className="grid grid-cols-3 gap-3 lg:col-span-5">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <dt className="text-xs text-slate-500">Completed trades</dt>
            <dd className="mt-1 flex items-center gap-1.5 font-mono text-2xl text-slate-900" data-testid="trader-completed-trades">
              <BadgeCheck className="size-5 text-green-600" aria-hidden />
              {rep?.completed_trades ?? "–"}
            </dd>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <dt className="text-xs text-slate-500">Verified rating</dt>
            <dd className="mt-1 font-mono text-2xl text-slate-900" data-testid="trader-average-rating">
              {rep?.average_rating != null ? rep.average_rating.toFixed(1) : "–"}
            </dd>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <dt className="text-xs text-slate-500">Reviews</dt>
            <dd className="mt-1 font-mono text-2xl text-slate-900" data-testid="trader-review-count">
              {rep ? rep.verified_review_count + rep.unverified_review_count : "–"}
            </dd>
          </div>
          <p className="col-span-3 text-xs text-slate-500">{rep?.note}</p>
        </dl>
      </section>

      <div className="grid gap-8 lg:grid-cols-12">
        <section className="space-y-4 lg:col-span-7">
          <h2 className="font-heading text-xl text-slate-900">Reviews</h2>
          {reputation.isLoading ? <div className="bx-shimmer h-24 rounded-2xl" /> : null}
          {rep && !rep.reviews.length ? (
            <p className="text-sm text-slate-500" data-testid="trader-reviews-empty">
              No reviews yet.
            </p>
          ) : null}
          <ul className="space-y-3" data-testid="trader-reviews">
            {rep?.reviews.map((review) => (
              <li key={review.id} className="bx-panel space-y-2 p-4" data-testid={`trader-review-${review.id}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm text-slate-900">{review.author?.name ?? "Trader"}</span>
                  <span className="flex items-center gap-2">
                    <Stars rating={review.rating} />
                    <span
                      className={`rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide ${
                        review.verified ? "bg-green-50 text-green-600" : "bg-slate-100 text-slate-500"
                      }`}
                      data-testid={`trader-review-${review.id}-verified`}
                    >
                      {review.verified ? "Verified trade" : "Unverified"}
                    </span>
                  </span>
                </div>
                {review.comment ? <p className="text-sm text-slate-700">{review.comment}</p> : null}
                <p className="font-mono text-[11px] text-slate-500">{shortDate(review.created_at)}</p>
              </li>
            ))}
          </ul>
        </section>

        <aside className="space-y-6 lg:col-span-5">
          {user && !isSelf && rep ? (
            <section className="bx-panel space-y-5 p-6" data-testid="trader-review-panel">
              <h2 className="font-heading text-lg text-slate-900">Review {rep.name}</h2>
              {rep.reviewable_exchanges.map((exchange) => (
                <div key={exchange.exchange_id} className="space-y-2">
                  <p className="text-xs text-slate-500">
                    Completed {exchange.cycle_type}-party exchange {exchange.completed_at ? `on ${shortDate(exchange.completed_at)}` : ""}
                  </p>
                  <ReviewForm
                    subjectId={id}
                    subjectName={rep.name}
                    exchangeId={exchange.exchange_id}
                    testId={`trader-verified-review-${exchange.exchange_id}`}
                  />
                </div>
              ))}
              {rep.viewer_can_review_unverified ? (
                <div className="space-y-2 border-t border-slate-200 pt-4">
                  <p className="text-xs text-slate-500">You haven't completed a trade with {rep.name}.</p>
                  <ReviewForm subjectId={id} subjectName={rep.name} testId="trader-unverified-review" />
                </div>
              ) : null}
              {!rep.reviewable_exchanges.length && !rep.viewer_can_review_unverified ? (
                <p className="text-sm text-slate-500" data-testid="trader-review-done">
                  You've already reviewed {rep.name}.
                </p>
              ) : null}
            </section>
          ) : null}

          <section className="bx-panel space-y-3 p-6">
            <h2 className="font-heading text-lg text-slate-900">Active listings</h2>
            {listings.data && !listings.data.length ? <p className="text-sm text-slate-500">Nothing listed right now.</p> : null}
            <ul className="space-y-2" data-testid="trader-listings">
              {listings.data?.map((listing) => (
                <li key={listing.id}>
                  <Link
                    to={`/listing/${listing.id}`}
                    className="flex items-center justify-between gap-3 rounded-lg px-2 py-1.5 text-sm text-slate-700 transition-colors duration-200 hover:bg-slate-100"
                    data-testid={`trader-listing-${listing.id}-link`}
                  >
                    <span>{listing.title}</span>
                    <span className="font-mono text-xs text-slate-500">{money(listing.estimated_value, listing.currency)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
    </div>
  );
}
