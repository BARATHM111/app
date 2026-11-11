import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles, Wand2 } from "lucide-react";
import { toast } from "sonner";

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
import { apiPost } from "@/lib/api";
import { CATEGORY_OPTIONS, CONDITION_OPTIONS } from "@/lib/categories";
import { extractErrorMessage } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { AnalyzeListingResponse, Listing, ListingPayload, ListingType } from "@/lib/types";

const EMPTY_FORM = {
  title: "",
  description: "",
  type: "goods" as ListingType,
  category: "Other",
  condition: "",
  estimated_value: 0,
  currency: "USD",
  location: "",
  tags: "",
};

export default function CreateListing() {
  const { user, isLoading } = useSession();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [source, setSource] = useState("");
  const [form, setForm] = useState(EMPTY_FORM);
  const [extraction, setExtraction] = useState<AnalyzeListingResponse | null>(null);

  const extract = useMutation({
    mutationFn: () => apiPost<AnalyzeListingResponse>("/v1/ai/analyze-listing", { text: source }),
    onSuccess: (data) => {
      const a = data.analysis;
      setExtraction(data);
      setForm((current) => ({
        title: a.name,
        description: a.description,
        type: a.listing_type,
        category: a.category,
        condition: a.condition ?? "",
        // No value basis means the field is left for the trader. AI never fills in a "verified" value.
        estimated_value: a.estimated_value ?? current.estimated_value,
        currency: a.currency ?? current.currency,
        location: user?.location ?? "",
        tags: a.keywords.join(", "),
      }));
      toast.success("Draft filled in. Review every field before publishing.");
    },
    onError: (error) =>
      toast.error(extractErrorMessage(error, "The listing reader is unavailable right now")),
  });

  const create = useMutation({
    mutationFn: (payload: ListingPayload) => apiPost<Listing>("/v1/listings", payload),
    onSuccess: async (listing) => {
      await queryClient.invalidateQueries({ queryKey: ["listings"] });
      await queryClient.invalidateQueries({ queryKey: ["matches"] });
      await queryClient.invalidateQueries({ queryKey: ["graph-stats"] });
      toast.success("Listing published");
      navigate(`/listing/${listing.id}`);
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not publish this listing")),
  });

  const update = (key: keyof typeof form) => (value: string | number) =>
    setForm((current) => ({ ...current, [key]: value }));

  if (isLoading) {
    return <div className="h-64 rounded-2xl border border-slate-200 bg-white bx-shimmer" />;
  }

  if (!user) {
    return (
      <div className="bx-panel mx-auto max-w-xl space-y-4 p-8 text-center" data-testid="create-listing-signin-prompt">
        <h1 className="font-heading text-2xl text-slate-900">Sign in to list something</h1>
        <p className="text-sm text-slate-500">
          Listings belong to a trader — sign in or create an account to publish goods or a service.
        </p>
        <div className="flex justify-center gap-3">
          <Link
            to="/login"
            className="rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-blue-600"
            data-testid="create-listing-signin-link"
          >
            Sign in
          </Link>
          <Link
            to="/register"
            className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm text-slate-900 transition-colors duration-200 hover:bg-slate-100"
            data-testid="create-listing-register-link"
          >
            Create account
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <h1 className="font-heading text-3xl font-semibold text-slate-900">List something to trade</h1>
        <p className="max-w-2xl text-slate-500">
          Describe it in your own words and let the listing reader fill the form, or type everything
          yourself. Either way, nothing is published until you press the button.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-12">
        <section className="bx-panel space-y-4 p-6 lg:col-span-5">
          <div className="flex items-center gap-2">
            <Wand2 className="size-4 text-fuchsia-300" aria-hidden />
            <h2 className="font-heading text-lg text-slate-900">AI listing reader</h2>
          </div>
          <p className="text-sm text-slate-500">
            Paste a rough description — a marketplace blurb works well. The reader proposes structured
            fields and flags anything it could not find.
          </p>
          <Textarea
            rows={8}
            value={source}
            onChange={(event) => setSource(event.target.value)}
            placeholder="Solid oak dining bench I built last winter, seats three, one small ding on the leg. Probably worth about 300 dollars, would swap for a decent espresso machine or camera gear."
            data-testid="create-listing-source-textarea"
          />
          <Button
            onClick={() => extract.mutate()}
            disabled={extract.isPending || source.trim().length < 10}
            className="w-full"
            data-testid="create-listing-extract-button"
          >
            <Sparkles className="size-4" aria-hidden />
            {extract.isPending ? "Reading your listing…" : "Read and fill the form"}
          </Button>

          {extract.isPending ? (
            <div className="bx-shimmer h-16 rounded-xl border border-slate-200" data-testid="create-listing-extract-loading" />
          ) : null}

          {extraction ? (
            <div className="bx-pop space-y-3 rounded-xl border border-blue-200 bg-blue-50 p-4" data-testid="create-listing-extraction">
              <div className="flex items-center justify-between gap-3">
                <p className="font-mono text-[11px] uppercase tracking-wide text-blue-600">
                  Draft from {extraction.model}
                </p>
                <span className="font-mono text-xs text-slate-700" data-testid="create-listing-confidence">
                  confidence {Math.round(extraction.analysis.confidence * 100)}%
                </span>
              </div>
              <p className="text-xs text-slate-500">{extraction.disclaimer}</p>
              <p className="text-xs text-slate-700" data-testid="create-listing-value-basis">
                Value:{" "}
                {extraction.analysis.value_basis === "stated_by_user"
                  ? "taken from your text"
                  : extraction.analysis.value_basis === "ai_estimate"
                    ? "rough AI estimate (unverified)"
                    : "not stated, so set it yourself"}
              </p>
              {extraction.analysis.warnings.length ? (
                <ul className="space-y-1.5 text-xs text-amber-700" data-testid="create-listing-warnings">
                  {extraction.analysis.warnings.map((warning) => (
                    <li key={warning} className="flex gap-2">
                      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-amber-400" />
                      {warning}
                    </li>
                  ))}
                </ul>
              ) : null}
              {Object.keys(extraction.analysis.attributes).length ? (
                <dl className="grid grid-cols-2 gap-2 text-xs" data-testid="create-listing-attributes">
                  {Object.entries(extraction.analysis.attributes).map(([key, value]) => (
                    <div key={key} className="rounded-lg bg-slate-50 px-2.5 py-1.5">
                      <dt className="text-slate-500">{key.replace(/_/g, " ")}</dt>
                      <dd className="text-slate-700">{String(value)}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
              {extraction.analysis.suggested_wants.length ? (
                <div className="space-y-2" data-testid="create-listing-suggested-wants">
                  <p className="font-mono text-[11px] uppercase tracking-wide text-slate-500">
                    You might want in return
                  </p>
                  <ul className="space-y-1.5">
                    {extraction.analysis.suggested_wants.map((want, index) => (
                      <li
                        key={want.title}
                        className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-2.5 py-1.5 text-xs"
                      >
                        <span className="text-slate-700">
                          {want.title} <span className="text-slate-500">· {want.category}</span>
                        </span>
                        <Link
                          to={`/wants?${new URLSearchParams({ title: want.title, category: want.category, target_type: want.target_type }).toString()}`}
                          className="shrink-0 text-blue-600 transition-colors duration-200 hover:text-blue-700"
                          data-testid={`create-listing-suggested-want-${index}-link`}
                        >
                          Add as want
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
        </section>

        <section className="bx-panel p-6 lg:col-span-7 sm:p-8">
          <form
            className="grid gap-5 sm:grid-cols-2"
            data-testid="create-listing-form"
            onSubmit={(event) => {
              event.preventDefault();
              create.mutate({
                title: form.title,
                description: form.description,
                type: form.type,
                category: form.category,
                condition: form.condition,
                estimated_value: Number(form.estimated_value),
                currency: form.currency,
                location: form.location || user.location || "",
                tags: form.tags
                  .split(",")
                  .map((tag) => tag.trim())
                  .filter(Boolean),
                status: "active",
                ai_assisted: Boolean(extraction),
              });
            }}
          >
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="listing-title">Title</Label>
              <Input
                id="listing-title"
                required
                minLength={2}
                value={form.title}
                onChange={(event) => update("title")(event.target.value)}
                placeholder="Handcrafted walnut writing desk"
                data-testid="create-listing-title-input"
              />
            </div>

            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="listing-description">Description</Label>
              <Textarea
                id="listing-description"
                rows={5}
                value={form.description}
                onChange={(event) => update("description")(event.target.value)}
                placeholder="Materials, size, condition, anything a trader should know."
                data-testid="create-listing-description-textarea"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="listing-type">Kind</Label>
              <Select value={form.type} onValueChange={(value: string) => update("type")(value as ListingType)}>
                <SelectTrigger id="listing-type" data-testid="create-listing-type-select">
                  <SelectValue>
                    {(value) => (value === "services" ? "Professional service" : "Physical goods")}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="goods">Physical goods</SelectItem>
                  <SelectItem value="services">Professional service</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="listing-category">Category</Label>
              <Select value={form.category} onValueChange={(value: string) => update("category")(value)}>
                <SelectTrigger id="listing-category" data-testid="create-listing-category-select">
                  <SelectValue>{(value) => String(value)}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {CATEGORY_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="listing-condition">Condition</Label>
              <Select value={form.condition || "Good"} onValueChange={(value: string) => update("condition")(value)}>
                <SelectTrigger id="listing-condition" data-testid="create-listing-condition-select">
                  <SelectValue>{(value) => String(value)}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {CONDITION_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="listing-value">Estimated value (USD)</Label>
              <Input
                id="listing-value"
                type="number"
                min={1}
                step="0.01"
                required
                value={form.estimated_value}
                onChange={(event) => update("estimated_value")(event.target.value)}
                data-testid="create-listing-value-input"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="listing-location">Location</Label>
              <Input
                id="listing-location"
                value={form.location}
                onChange={(event) => update("location")(event.target.value)}
                placeholder="Austin, TX"
                data-testid="create-listing-location-input"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="listing-tags">Tags (comma separated)</Label>
              <Input
                id="listing-tags"
                value={form.tags}
                onChange={(event) => update("tags")(event.target.value)}
                placeholder="walnut, desk, handmade"
                data-testid="create-listing-tags-input"
              />
            </div>

            <div className="sm:col-span-2">
              <Button
                type="submit"
                className="w-full"
                disabled={create.isPending}
                data-testid="create-listing-submit-button"
              >
                {create.isPending ? "Publishing…" : "Publish listing"}
              </Button>
              <p className="mt-3 text-xs text-slate-500">
                AI-suggested values are estimates, not verified valuations. You can edit any listing you own
                from your dashboard.
              </p>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
