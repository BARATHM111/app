import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Brain, GitBranch, Handshake, Search, ShieldCheck, Wallet } from "lucide-react";

import CycleGraph from "@/components/CycleGraph";
import { apiGet } from "@/lib/api";
import type { Cycle, GraphStats } from "@/lib/types";

// Static showcase cycle — the landing page renders with or without a backend.
const DEMO_CYCLE: Cycle = {
  key: "c3:demo",
  id: "c3:demo",
  status: "discovered",
  min_edge_score: 0.72,
  avg_edge_score: 0.8,
  rank: 1,
  reasons: [],
  cycle_type: 3,
  participant_ids: ["maya", "theo", "ravi"],
  participants: [
    {
      user_id: "maya",
      user_name: "Maya · walnut desk",
      gives_listing_id: "l1",
      gives_listing_title: "Walnut writing desk",
      gives_value: 450,
      receives_listing_id: "l3",
      receives_listing_title: "Brand identity package",
      receives_value: 480,
      balance_amount: 30,
      currency: "USD",
    },
    {
      user_id: "theo",
      user_name: "Theo · camera kit",
      gives_listing_id: "l2",
      gives_listing_title: "35mm rangefinder kit",
      gives_value: 520,
      receives_listing_id: "l1",
      receives_listing_title: "Walnut writing desk",
      receives_value: 450,
      balance_amount: -70,
      currency: "USD",
    },
    {
      user_id: "ravi",
      user_name: "Ravi · brand design",
      gives_listing_id: "l3",
      gives_listing_title: "Brand identity package",
      gives_value: 480,
      receives_listing_id: "l2",
      receives_listing_title: "35mm rangefinder kit",
      receives_value: 520,
      balance_amount: 40,
      currency: "USD",
    },
  ],
  total_value: 1450,
  total_imbalance: 140,
  mean_semantic_score: 0.71,
  edges: [],
};

const STEPS = [
  {
    icon: Search,
    title: "Describe what you have",
    body: "Paste a rough description. The listing reader pulls out title, category, condition and a fair value estimate for you to review.",
  },
  {
    icon: GitBranch,
    title: "The graph finds the loop",
    body: "Deterministic code builds the trade graph and finds two-person swaps and three-person cycles where everybody's want is filled.",
  },
  {
    icon: Handshake,
    title: "Everyone approves, then it happens",
    body: "A proposal needs every participant's approval. Change the terms and the earlier approvals are invalidated — automatically.",
  },
];

export default function Home() {
  const stats = useQuery({
    queryKey: ["graph-stats"],
    queryFn: () => apiGet<GraphStats>("/v1/graph/stats"),
    retry: false,
  });

  return (
    <div className="space-y-16">
      <section className="grid gap-10 lg:grid-cols-12 lg:items-start">
        <div className="space-y-6 lg:col-span-7">
          <span className="inline-flex items-center gap-2 rounded-full border border-blue-300 bg-blue-50 px-3 py-1 font-mono text-xs uppercase tracking-wide text-blue-600">
            Barter exchange · not a shop
          </span>
          <h1 className="font-heading text-4xl font-semibold leading-[1.08] text-slate-900 sm:text-5xl lg:text-[3.4rem]">
            Trade what you have for what you actually need.
          </h1>
          <p className="max-w-2xl text-lg leading-relaxed text-slate-500">
            BarterX is a marketplace for goods and professional services where nobody pays full price in
            cash. List something, say what you want back, and let the engine find a trade — including
            three-way cycles where no two people can swap directly.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Link
              to="/marketplace"
              className="inline-flex items-center gap-2 rounded-xl bg-blue-700 px-5 py-3 text-sm font-medium text-white transition-colors duration-200 hover:bg-blue-600"
              data-testid="home-browse-marketplace-link"
            >
              Browse the marketplace
              <ArrowRight className="size-4" aria-hidden />
            </Link>
            <Link
              to="/cycles"
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-5 py-3 text-sm text-slate-900 transition-colors duration-200 hover:bg-slate-100"
              data-testid="home-view-cycles-link"
            >
              <GitBranch className="size-4" aria-hidden />
              See a live cycle
            </Link>
          </div>

          <dl className="grid max-w-xl grid-cols-2 gap-4 pt-4 sm:grid-cols-4">
            <Stat label="Traders" value={stats.data ? String(stats.data.nodes) : "—"} />
            <Stat label="Trade edges" value={stats.data ? String(stats.data.edges) : "—"} />
            <Stat label="2-party cycles" value={stats.data ? String(stats.data.two_cycles) : "—"} />
            <Stat label="3-party cycles" value={stats.data ? String(stats.data.three_cycles) : "—"} />
          </dl>
          {stats.isError ? (
            <p className="font-mono text-xs text-amber-600" data-testid="home-stats-degraded">
              Live engine stats are unavailable right now — the rest of the page is unaffected.
            </p>
          ) : null}
        </div>

        <div className="bx-panel space-y-4 p-6 lg:col-span-5" data-testid="home-cycle-showcase">
          <div className="flex items-baseline justify-between gap-4">
            <h2 className="font-heading text-lg font-semibold text-slate-900">A discovered 3-party cycle</h2>
            <span className="font-mono text-[11px] uppercase tracking-wide text-slate-500">
              deterministic
            </span>
          </div>
          <CycleGraph cycle={DEMO_CYCLE} />
          <p className="text-sm leading-relaxed text-slate-500">
            Nobody here has what the other wants directly. The cycle closes with a{" "}
            <span className="font-mono text-blue-600">$70.00</span> balancing payment from the two traders who
            received more value than they gave — authorised by them, never by the software.
          </p>
        </div>
      </section>

      <section className="space-y-6">
        <h2 className="font-heading text-2xl font-semibold text-slate-900">How a barter cycle happens</h2>
        <div className="grid gap-6 md:grid-cols-3">
          {STEPS.map(({ icon: Icon, title, body }, index) => (
            <div key={title} className="bx-panel p-6">
              <div className="flex items-center gap-3">
                <span className="grid size-9 place-items-center rounded-lg bg-slate-100 text-blue-600">
                  <Icon className="size-4" aria-hidden />
                </span>
                <span className="font-mono text-xs text-slate-500">0{index + 1}</span>
              </div>
              <h3 className="mt-4 font-heading text-lg font-medium text-slate-900">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-500">{body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-12">
        <div className="bx-panel space-y-4 p-6 lg:col-span-7">
          <div className="flex items-center gap-3">
            <Brain className="size-5 text-fuchsia-300" aria-hidden />
            <h2 className="font-heading text-lg font-semibold text-slate-900">
              What the AI does — and what it never touches
            </h2>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-wide text-fuchsia-300">AI assists</p>
              <ul className="mt-2 space-y-1.5 text-sm text-slate-700">
                <li>Reading a messy description into structured fields</li>
                <li>Suggesting a category</li>
                <li>Explaining why two listings look compatible</li>
                <li>Summarising a proposal and suggesting negotiation options</li>
              </ul>
            </div>
            <div>
              <p className="font-mono text-[11px] uppercase tracking-wide text-green-600">
                Deterministic code decides
              </p>
              <ul className="mt-2 space-y-1.5 text-sm text-slate-700">
                <li>Compatibility validation</li>
                <li>Value maths and balancing payments</li>
                <li>Cycle discovery and approval state</li>
                <li>Payment initiation and verification</li>
              </ul>
            </div>
          </div>
        </div>

        <div className="space-y-6 lg:col-span-5">
          <div className="bx-panel space-y-3 p-6">
            <div className="flex items-center gap-3">
              <Wallet className="size-5 text-blue-600" aria-hidden />
              <h2 className="font-heading text-lg font-semibold text-slate-900">Balancing payments</h2>
            </div>
            <p className="text-sm leading-relaxed text-slate-500">
              When a cycle is not perfectly balanced, the traders who received more value pay the
              difference through PayPal Sandbox — and only after they authorise it themselves.
            </p>
            <p className="flex gap-2 text-xs leading-relaxed text-slate-500">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-green-600" aria-hidden />
              A payment is only ever marked successful from PayPal's own server-side answer. PayPal is not an
              escrow service.
            </p>
          </div>

          <div className="bx-panel space-y-3 p-6" data-testid="home-demo-accounts">
            <h2 className="font-heading text-lg font-semibold text-slate-900">Demo traders</h2>
            <p className="text-sm text-slate-500">
              Seven seeded traders with listings, wants and two live cycles. Password for all of them:{" "}
              <span className="font-mono text-blue-600">barter1234</span>
            </p>
            <ul className="grid grid-cols-1 gap-1 font-mono text-xs text-slate-500 sm:grid-cols-2">
              <li>maya@barterx.dev</li>
              <li>theo@barterx.dev</li>
              <li>ravi@barterx.dev</li>
              <li>sana@barterx.dev</li>
              <li>diego@barterx.dev</li>
              <li>nia@barterx.dev</li>
              <li>omar@barterx.dev</li>
            </ul>
            <Link
              to="/login"
              className="inline-flex text-sm font-medium text-blue-600 transition-colors duration-200 hover:text-blue-700"
              data-testid="home-demo-sign-in-link"
            >
              Sign in as a demo trader →
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
      <dt className="text-[11px] uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 font-mono text-xl text-slate-900">{value}</dd>
    </div>
  );
}
