import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { CategoryChip, StatusBadge } from "@/components/Badges";
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
import { Textarea } from "@/components/ui/textarea";
import { apiDelete, apiGet, apiPost } from "@/lib/api";
import { CATEGORY_OPTIONS } from "@/lib/categories";
import { extractErrorMessage, money } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { MessageResponse, Want, WantListResponse, WantPayload } from "@/lib/types";

const EMPTY_WANT = {
  title: "",
  description: "",
  category: "",
  target_type: "any" as "goods" | "services" | "any",
  min_value: 0,
  max_value: 500,
  keywords: "",
  listing_id: "none",
  min_condition: "",
  location_preference: "any" as "any" | "local",
};

export default function Wants() {
  const { user, isLoading } = useSession();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  // Prefill from an AI-suggested want ("Add as want" on the create-listing page).
  const [form, setForm] = useState<typeof EMPTY_WANT>(() => {
    const target = searchParams.get("target_type");
    return {
      ...EMPTY_WANT,
      title: searchParams.get("title") ?? "",
      category: searchParams.get("category") ?? "",
      target_type: (target === "goods" || target === "services" ? target : "any") as typeof EMPTY_WANT.target_type,
    };
  });

  const wants = useQuery({
    queryKey: ["wants"],
    queryFn: () => apiGet<WantListResponse>("/v1/wants"),
    enabled: Boolean(user),
    retry: false,
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["wants"] });
    await queryClient.invalidateQueries({ queryKey: ["matches"] });
    await queryClient.invalidateQueries({ queryKey: ["graph-stats"] });
  };

  const createWant = useMutation({
    mutationFn: (payload: WantPayload) => apiPost<Want>("/v1/wants", payload),
    onSuccess: async () => {
      await invalidate();
      setForm(EMPTY_WANT);
      toast.success("Want saved — matches refresh automatically");
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not save that want")),
  });

  const deleteWant = useMutation({
    mutationFn: (wantId: string) => apiDelete<MessageResponse>(`/v1/wants/${wantId}`),
    onSuccess: async () => {
      await invalidate();
      toast.success("Want removed");
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not remove that want")),
  });

  const update = (key: keyof typeof form) => (value: string | number) =>
    setForm((current) => ({ ...current, [key]: value }));

  if (isLoading) {
    return <div className="h-64 rounded-2xl border border-slate-200 bg-white bx-shimmer" />;
  }

  if (!user) {
    return (
      <div className="bx-panel mx-auto max-w-xl space-y-4 p-8 text-center" data-testid="wants-signin-prompt">
        <h1 className="font-heading text-2xl text-slate-900">Sign in to manage your wants</h1>
        <Link
          to="/login"
          className="inline-flex rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-blue-600"
          data-testid="wants-signin-link"
        >
          Sign in
        </Link>
      </div>
    );
  }

  const listingOptions = wants.data?.listing_options ?? [];
  const myWants = wants.data?.wants ?? [];

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <h1 className="font-heading text-3xl font-semibold text-slate-900">My wants</h1>
        <p className="max-w-2xl text-slate-500">
          A want says what you are looking for. Attach the listing you are offering in return and the want
          becomes part of the trade graph — that is what lets a cycle close.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-12">
        <section className="bx-panel space-y-4 p-6 lg:col-span-7">
          <h2 className="font-heading text-lg text-slate-900">Open wants</h2>
          {wants.isError ? (
            <p className="text-sm text-amber-700" data-testid="wants-error">
              Wants could not be loaded right now.
            </p>
          ) : null}
          {!wants.isLoading && myWants.length === 0 ? (
            <p className="text-sm text-slate-500" data-testid="wants-empty">
              No wants yet. Describe the thing you would trade your listing for.
            </p>
          ) : null}
          <ul className="space-y-3" data-testid="wants-list">
            {myWants.map((want) => (
              <li
                key={want.id}
                className="rounded-xl border border-slate-200 bg-slate-50 p-4"
                data-testid={`want-item-${want.id}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={want.status === "open" ? "active" : "archived"} />
                      <CategoryChip category={want.category || "Any category"} />
                      <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-700">
                        {want.target_type === "any" ? "goods or services" : want.target_type}
                      </span>
                    </div>
                    <p className="font-medium text-slate-900">{want.title}</p>
                    <p className="line-clamp-2 text-sm text-slate-500">{want.description}</p>
                    <p className="font-mono text-xs text-slate-500">
                      {money(want.min_value, want.currency)} – {money(want.max_value, want.currency)}
                    </p>
                    <p className="text-xs text-slate-500" data-testid={`want-item-${want.id}-offering`}>
                      {want.offered_listing
                        ? `Offering: ${want.offered_listing.title} (${money(want.offered_listing.estimated_value, want.offered_listing.currency)})`
                        : "No offering attached — this want cannot join a cycle yet"}
                    </p>
                  </div>
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    aria-label="Delete want"
                    onClick={() => deleteWant.mutate(want.id)}
                    disabled={deleteWant.isPending}
                    data-testid={`want-item-${want.id}-delete-button`}
                  >
                    <Trash2 className="size-4" aria-hidden />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="bx-panel p-6 lg:col-span-5">
          <h2 className="font-heading text-lg text-slate-900">Add a want</h2>
          <form
            className="mt-4 space-y-4"
            data-testid="want-form"
            onSubmit={(event) => {
              event.preventDefault();
              createWant.mutate({
                title: form.title,
                description: form.description,
                category: form.category,
                target_type: form.target_type,
                min_condition: form.min_condition || null,
                location_preference: form.location_preference,
                min_value: Number(form.min_value),
                max_value: Number(form.max_value),
                currency: "USD",
                keywords: form.keywords
                  .split(",")
                  .map((keyword) => keyword.trim())
                  .filter(Boolean),
                listing_id: form.listing_id === "none" ? null : form.listing_id,
              });
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="want-title">What do you want?</Label>
              <Input
                id="want-title"
                required
                minLength={2}
                value={form.title}
                onChange={(event) => update("title")(event.target.value)}
                placeholder="Brand identity for my studio"
                data-testid="want-title-input"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="want-description">Details</Label>
              <Textarea
                id="want-description"
                rows={3}
                value={form.description}
                onChange={(event) => update("description")(event.target.value)}
                placeholder="Deliverables, style, timeline."
                data-testid="want-description-textarea"
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="want-category">Category</Label>
                <Select value={form.category || "any"} onValueChange={(value: string) => update("category")(value === "any" ? "" : value)}>
                  <SelectTrigger id="want-category" data-testid="want-category-select">
                    <SelectValue>{(value) => (value === "any" ? "Any category" : String(value))}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Any category</SelectItem>
                    {CATEGORY_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="want-target-type">Accept</Label>
                <Select
                  value={form.target_type}
                  onValueChange={(value: string) => update("target_type")(value)}
                >
                  <SelectTrigger id="want-target-type" data-testid="want-target-type-select">
                    <SelectValue>
                      {(value) =>
                        ({ any: "Goods or services", goods: "Goods only", services: "Services only" })[
                          value as string
                        ] ?? "Goods or services"
                      }
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Goods or services</SelectItem>
                    <SelectItem value="goods">Goods only</SelectItem>
                    <SelectItem value="services">Services only</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="want-min-condition">Minimum condition</Label>
                <select
                  id="want-min-condition"
                  className="h-9 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
                  value={form.min_condition}
                  onChange={(event) => setForm((current) => ({ ...current, min_condition: event.target.value }))}
                  data-testid="want-min-condition-select"
                >
                  <option value="">Any condition</option>
                  {["New", "Like new", "Excellent", "Good", "Fair"].map((condition) => (
                    <option key={condition} value={condition}>{condition} or better</option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="want-location">Location</Label>
                <select
                  id="want-location"
                  className="h-9 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
                  value={form.location_preference}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, location_preference: event.target.value === "local" ? "local" : "any" }))
                  }
                  data-testid="want-location-select"
                >
                  <option value="any">Anywhere (remote or shipped)</option>
                  <option value="local">Local only (my city)</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="want-min">Minimum value (USD)</Label>
                <Input
                  id="want-min"
                  type="number"
                  min={0}
                  value={form.min_value}
                  onChange={(event) => update("min_value")(event.target.value)}
                  data-testid="want-min-value-input"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="want-max">Maximum value (USD)</Label>
                <Input
                  id="want-max"
                  type="number"
                  min={1}
                  value={form.max_value}
                  onChange={(event) => update("max_value")(event.target.value)}
                  data-testid="want-max-value-input"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="want-keywords">Keywords (comma separated)</Label>
              <Input
                id="want-keywords"
                value={form.keywords}
                onChange={(event) => update("keywords")(event.target.value)}
                placeholder="branding, logo, identity"
                data-testid="want-keywords-input"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="want-offering">What you offer in return</Label>
              <Select value={form.listing_id} onValueChange={(value: string) => update("listing_id")(value)}>
                <SelectTrigger id="want-offering" data-testid="want-offering-select">
                  <SelectValue>
                    {(value) =>
                      value === "none"
                        ? "Nothing yet"
                        : listingOptions.find((option) => option.id === value)?.title ?? String(value)
                    }
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Nothing yet</SelectItem>
                  {listingOptions.map((option) => (
                    <SelectItem key={option.id} value={option.id}>
                      {option.title} · {money(option.estimated_value, option.currency)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {listingOptions.length === 0 ? (
                <p className="text-xs text-slate-500">
                  You have no uncommitted active listing yet —{" "}
                  <Link
                    to="/create-listing"
                    className="text-blue-600 transition-colors duration-200 hover:text-blue-700"
                    data-testid="want-create-listing-link"
                  >
                    list something first
                  </Link>
                  .
                </p>
              ) : null}
            </div>
            <Button
              type="submit"
              className="w-full"
              disabled={createWant.isPending}
              data-testid="want-submit-button"
            >
              <Plus className="size-4" aria-hidden />
              {createWant.isPending ? "Saving…" : "Save want"}
            </Button>
          </form>
        </section>
      </div>
    </div>
  );
}
