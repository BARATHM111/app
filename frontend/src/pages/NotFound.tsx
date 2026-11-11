import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="bx-panel mx-auto max-w-xl space-y-4 p-8 text-center" data-testid="not-found-page">
      <p className="font-mono text-xs uppercase tracking-wide text-slate-500">404</p>
      <h1 className="font-heading text-2xl font-semibold text-slate-900">That page doesn't exist</h1>
      <p className="text-sm text-slate-500">
        The link may be stale. Everything worth seeing starts from the marketplace or the cycles page.
      </p>
      <div className="flex justify-center gap-3 pt-1">
        <Link
          to="/marketplace"
          className="rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-blue-600"
          data-testid="not-found-marketplace-link"
        >
          Marketplace
        </Link>
        <Link
          to="/cycles"
          className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm text-slate-900 transition-colors duration-200 hover:bg-slate-100"
          data-testid="not-found-cycles-link"
        >
          Cycles
        </Link>
      </div>
    </div>
  );
}
