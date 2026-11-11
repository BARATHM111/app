import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, SlidersHorizontal } from "lucide-react";

import ListingCard from "@/components/ListingCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { apiGet } from "@/lib/api";
import { CATEGORY_OPTIONS } from "@/lib/categories";
import type { ListingPage } from "@/lib/types";

const PAGE_SIZE = 12;

export default function Marketplace() {
  const [search, setSearch] = useState("");
  const [type, setType] = useState("any");
  const [category, setCategory] = useState("any");
  const [sort, setSort] = useState("recent");
  const [minValue, setMinValue] = useState("");
  const [maxValue, setMaxValue] = useState("");
  const [page, setPage] = useState(1);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    params.set("page", String(page));
    params.set("page_size", String(PAGE_SIZE));
    params.set("sort", sort);
    params.set("status", "active");
    if (search.trim()) params.set("q", search.trim());
    if (type !== "any") params.set("type", type);
    if (category !== "any") params.set("category", category);
    if (minValue) params.set("min_value", minValue);
    if (maxValue) params.set("max_value", maxValue);
    return params.toString();
  }, [search, type, category, sort, minValue, maxValue, page]);

  const listings = useQuery({
    queryKey: ["listings", query],
    queryFn: () => apiGet<ListingPage>(`/v1/listings?${query}`),
    retry: false,
  });

  const items = listings.data?.items ?? [];
  const pages = listings.data?.pages ?? 1;

  const resetFilters = () => {
    setSearch("");
    setType("any");
    setCategory("any");
    setSort("recent");
    setMinValue("");
    setMaxValue("");
    setPage(1);
  };

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <h1 className="font-heading text-3xl font-semibold text-slate-900">Marketplace</h1>
        <p className="max-w-2xl text-slate-500">
          Goods and professional services listed for trade. Values shown are the trader's own estimates —
          never verified valuations.
        </p>
      </div>

      <section className="bx-panel space-y-5 p-6" data-testid="marketplace-filters">
        <div className="flex items-center gap-2 text-sm text-slate-700">
          <SlidersHorizontal className="size-4 text-blue-600" aria-hidden />
          Filters
        </div>
        <div className="grid gap-4 lg:grid-cols-12">
          <div className="space-y-2 lg:col-span-4">
            <Label htmlFor="marketplace-search">Search</Label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" aria-hidden />
              <Input
                id="marketplace-search"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
                placeholder="walnut desk, camera, branding…"
                className="pl-9"
                data-testid="marketplace-search-input"
              />
            </div>
          </div>

          <div className="space-y-2 lg:col-span-2">
            <Label htmlFor="marketplace-type">Kind</Label>
            <Select
              value={type}
              onValueChange={(value: string) => {
                setType(value);
                setPage(1);
              }}
            >
              <SelectTrigger id="marketplace-type" data-testid="marketplace-type-select">
                <SelectValue>
                  {(value) => ({ any: "Goods & services", goods: "Physical goods", services: "Services" })[value as string] ?? "Any"}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="any">Goods &amp; services</SelectItem>
                <SelectItem value="goods">Physical goods</SelectItem>
                <SelectItem value="services">Services</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2 lg:col-span-2">
            <Label htmlFor="marketplace-category">Category</Label>
            <Select
              value={category}
              onValueChange={(value: string) => {
                setCategory(value);
                setPage(1);
              }}
            >
              <SelectTrigger id="marketplace-category" data-testid="marketplace-category-select">
                <SelectValue>{(value) => (value === "any" ? "All categories" : String(value))}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="any">All categories</SelectItem>
                {CATEGORY_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2 lg:col-span-2">
            <Label htmlFor="marketplace-min">Min value (USD)</Label>
            <Input
              id="marketplace-min"
              type="number"
              min={0}
              value={minValue}
              onChange={(event) => {
                setMinValue(event.target.value);
                setPage(1);
              }}
              placeholder="0"
              data-testid="marketplace-min-value-input"
            />
          </div>

          <div className="space-y-2 lg:col-span-2">
            <Label htmlFor="marketplace-max">Max value (USD)</Label>
            <Input
              id="marketplace-max"
              type="number"
              min={0}
              value={maxValue}
              onChange={(event) => {
                setMaxValue(event.target.value);
                setPage(1);
              }}
              placeholder="1000"
              data-testid="marketplace-max-value-input"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Select
            value={sort}
            onValueChange={(value: string) => setSort(value)}
          >
            <SelectTrigger size="sm" className="w-48" data-testid="marketplace-sort-select">
              <SelectValue>
                {(value) =>
                  ({
                    recent: "Newest first",
                    oldest: "Oldest first",
                    value_asc: "Value: low to high",
                    value_desc: "Value: high to low",
                  })[value as string] ?? "Newest first"
                }
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="recent">Newest first</SelectItem>
              <SelectItem value="oldest">Oldest first</SelectItem>
              <SelectItem value="value_asc">Value: low to high</SelectItem>
              <SelectItem value="value_desc">Value: high to low</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="ghost" size="sm" onClick={resetFilters} data-testid="marketplace-reset-button">
            Reset filters
          </Button>
        </div>
      </section>

      {listings.isError ? (
        <p
          className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700"
          data-testid="marketplace-error"
        >
          Listings could not be loaded. The marketplace is empty right now — try again in a moment.
        </p>
      ) : null}

      {listings.isLoading ? (
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3" data-testid="marketplace-loading">
          {[0, 1, 2, 3, 4, 5].map((key) => (
            <div key={key} className="h-64 rounded-2xl border border-slate-200 bg-white bx-shimmer" />
          ))}
        </div>
      ) : null}

      {!listings.isLoading && items.length === 0 ? (
        <div className="bx-panel p-8 text-center" data-testid="marketplace-empty-state">
          <p className="font-heading text-lg text-slate-900">No listings match those filters</p>
          <p className="mt-2 text-sm text-slate-500">
            Try widening the value range, or be the first to list something in this category.
          </p>
        </div>
      ) : null}

      {items.length ? (
        <section className="grid gap-6 md:grid-cols-2 xl:grid-cols-3" data-testid="marketplace-results">
          {items.map((listing, index) => (
            <div key={listing.id} className={index === 0 ? "md:col-span-2 xl:col-span-2" : ""}>
              <ListingCard listing={listing} featured={index === 0} />
            </div>
          ))}
        </section>
      ) : null}

      {pages > 1 ? (
        <div className="flex items-center justify-between gap-4">
          <span className="font-mono text-xs text-slate-500">
            Page {listings.data?.page ?? 1} of {pages} · {listings.data?.total ?? 0} listings
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              data-testid="marketplace-prev-page-button"
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= pages}
              onClick={() => setPage((current) => current + 1)}
              data-testid="marketplace-next-page-button"
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
