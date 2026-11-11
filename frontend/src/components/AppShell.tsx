import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Bell,
  Compass,
  GitBranch,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Plus,
  ShieldAlert,
  Sparkles,
  UserRound,
} from "lucide-react";
import { toast } from "sonner";

import { Toaster } from "@/components/ui/sonner";
import { apiGet } from "@/lib/api";
import { endSession, useSession } from "@/lib/session";
import type { UnreadCountResponse } from "@/lib/types";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, slug: "dashboard" },
  { to: "/marketplace", label: "Marketplace", icon: Compass, slug: "marketplace" },
  { to: "/matches", label: "Matches", icon: Sparkles, slug: "matches" },
  { to: "/cycles", label: "Cycles", icon: GitBranch, slug: "cycles" },
  { to: "/wants", label: "My wants", icon: ListChecks, slug: "wants" },
  { to: "/notifications", label: "Notifications", icon: Bell, slug: "notifications" },
];

function navClass({ isActive }: { isActive: boolean }) {
  return `flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm transition-colors duration-200 ${
    isActive ? "bg-blue-50 font-semibold text-blue-600" : "font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900"
  }`;
}

export default function AppShell() {
  const { user } = useSession();
  const navigate = useNavigate();

  // Unread count is decoration: the shell renders identically when the call fails.
  const unread = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => apiGet<UnreadCountResponse>("/v1/notifications/unread"),
    enabled: Boolean(user),
    retry: false,
  });

  const signOut = useMutation({
    mutationFn: endSession,
    onSuccess: () => {
      toast.success("Signed out");
      navigate("/");
    },
  });

  const unreadCount = unread.data?.unread ?? 0;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <Toaster richColors theme="light" position="top-right" />
      <div className="mx-auto flex max-w-[1500px] gap-6 p-4 lg:p-5">
        <aside
          className="sticky top-5 hidden h-[calc(100vh-2.5rem)] w-64 shrink-0 flex-col rounded-2xl border border-slate-200/80 bg-white p-4 shadow-xs lg:flex"
          data-testid="app-sidebar"
        >
          <Link to="/" className="mb-6 flex items-center gap-2.5 px-2" data-testid="sidebar-brand-link">
            <span className="grid size-9 place-items-center rounded-xl bg-blue-600 font-heading text-lg font-bold text-white">B</span>
            <span className="font-heading text-xl font-semibold text-blue-600">BarterX</span>
          </Link>
          <nav className="flex flex-col gap-1" aria-label="Main">
            {NAV.map(({ to, label, icon: Icon, slug }) => (
              <NavLink key={to} to={to} className={navClass} data-testid={`sidebar-nav-${slug}`}>
                <Icon className="size-4" aria-hidden />
                <span className="flex-1">{label}</span>
                {slug === "notifications" && unreadCount > 0 ? (
                  <span className="rounded-full bg-blue-600 px-1.5 text-[11px] font-semibold text-white" data-testid="sidebar-unread-count">
                    {unreadCount}
                  </span>
                ) : null}
              </NavLink>
            ))}
            {user ? (
              <NavLink to={`/trader/${user.id}`} className={navClass} data-testid="sidebar-nav-profile">
                <UserRound className="size-4" aria-hidden />
                <span>My profile</span>
              </NavLink>
            ) : null}
            {user?.role === "admin" ? (
              <>
                <p className="mt-5 px-3.5 text-xs font-medium text-slate-400">Admin</p>
                <NavLink to="/admin/disputes" className={navClass} data-testid="sidebar-nav-admin-disputes">
                  <ShieldAlert className="size-4" aria-hidden />
                  <span>Disputes</span>
                </NavLink>
              </>
            ) : null}
          </nav>
          <div className="mt-auto rounded-xl bg-slate-50 p-3 text-xs text-slate-500">
            AI suggestions are not verified valuations. PayPal Sandbox moves agreed balances. It is not an escrow service.
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <header
            className="mb-6 flex items-center justify-between gap-3 rounded-2xl border border-slate-200/80 bg-white/80 px-4 py-3 shadow-xs backdrop-blur-md sm:px-5"
            data-testid="app-header"
          >
            <Link to="/" className="font-heading text-lg font-semibold text-blue-600 lg:hidden" data-testid="header-brand-link">
              BarterX
            </Link>
            <nav className="flex gap-1 overflow-x-auto lg:hidden" aria-label="Mobile">
              {NAV.slice(0, 4).map(({ to, label, slug }) => (
                <NavLink key={to} to={to} className={navClass} data-testid={`header-nav-${slug}`}>
                  {label}
                </NavLink>
              ))}
            </nav>
            <p className="hidden text-sm text-slate-500 lg:block" data-testid="header-greeting">
              {user ? `Welcome back, ${user.name.split(" ")[0]}` : "Trade goods and skills in fair cycles"}
            </p>
            <div className="flex items-center gap-2">
              {user ? (
                <>
                  <Link to="/create-listing" className="inline-flex h-8 items-center gap-1.5 rounded-xl bg-blue-600 px-3 text-sm font-medium text-white transition-colors duration-200 hover:bg-blue-700" data-testid="header-create-listing-button">
                    <Plus className="size-4" aria-hidden /> List
                  </Link>
                  <Link
                    to="/notifications"
                    className="relative grid size-9 place-items-center rounded-full border border-slate-200 text-slate-600 transition-colors duration-200 hover:bg-slate-100"
                    data-testid="header-notifications-link"
                    aria-label="Notifications"
                  >
                    <Bell className="size-4" aria-hidden />
                    {unreadCount > 0 ? <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-red-500" /> : null}
                  </Link>
                  <Link
                    to={`/trader/${user.id}`}
                    className="grid size-9 place-items-center rounded-full bg-blue-50 font-heading text-sm font-semibold text-blue-700"
                    data-testid="header-avatar-link"
                    aria-label="My profile"
                  >
                    {user.name.slice(0, 1).toUpperCase()}
                  </Link>
                  <button
                    type="button"
                    onClick={() => signOut.mutate()}
                    className="grid size-9 place-items-center rounded-full text-slate-500 transition-colors duration-200 hover:bg-slate-100 hover:text-slate-900"
                    data-testid="header-signout-button"
                    aria-label="Sign out"
                  >
                    <LogOut className="size-4" aria-hidden />
                  </button>
                </>
              ) : (
                <>
                  <Link to="/login" className="px-3 text-sm font-medium text-slate-600 hover:text-slate-900" data-testid="header-signin-link">
                    Sign in
                  </Link>
                  <Link to="/register" className="inline-flex h-8 items-center gap-1.5 rounded-xl bg-blue-600 px-3 text-sm font-medium text-white transition-colors duration-200 hover:bg-blue-700" data-testid="header-register-button">
                    Create account
                  </Link>
                </>
              )}
            </div>
          </header>
          <main className="pb-10" data-testid="app-main">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
