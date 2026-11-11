import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { GitBranch, Repeat2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiPost } from "@/lib/api";
import { extractErrorMessage } from "@/lib/format";
import { beginSession } from "@/lib/session";
import type { UserMe } from "@/lib/types";

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const signIn = useMutation({
    mutationFn: (payload: { email: string; password: string }) =>
      apiPost<UserMe>("/v1/auth/login", payload),
    onSuccess: async (user) => {
      await beginSession();
      toast.success(`Welcome back, ${user.name}`);
      navigate("/dashboard");
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not sign in")),
  });

  return (
    <div className="grid gap-10 lg:grid-cols-12 lg:items-center">
      <div className="space-y-5 lg:col-span-6">
        <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1 font-mono text-xs uppercase tracking-wide text-slate-500">
          Sign in
        </span>
        <h1 className="font-heading text-3xl font-semibold text-slate-900 sm:text-4xl">
          Pick up your trades where you left them.
        </h1>
        <p className="max-w-lg text-slate-500">
          Your listings, wants and proposals live behind a session cookie — no tokens in the browser, and
          signing out clears everything this browser cached.
        </p>
        <ul className="space-y-3 text-sm text-slate-700">
          <li className="flex gap-2">
            <Repeat2 className="mt-0.5 size-4 shrink-0 text-blue-600" aria-hidden />
            Every participant of a cycle approves before anything moves.
          </li>
          <li className="flex gap-2">
            <GitBranch className="mt-0.5 size-4 shrink-0 text-blue-600" aria-hidden />
            Two-person swaps and three-person cycles, discovered deterministically.
          </li>
        </ul>
        <div className="bx-panel p-4 text-sm text-slate-500">
          <p className="font-mono text-xs uppercase tracking-wide text-slate-500">Demo traders</p>
          <p className="mt-1.5">
            <span className="font-mono text-blue-600">maya@barterx.dev</span> ·{" "}
            <span className="font-mono text-blue-600">sana@barterx.dev</span> · password{" "}
            <span className="font-mono text-blue-600">barter1234</span>
          </p>
        </div>
      </div>

      <div className="bx-panel p-6 lg:col-span-6 sm:p-8">
        <form
          className="space-y-5"
          data-testid="login-form"
          onSubmit={(event) => {
            event.preventDefault();
            signIn.mutate({ email, password });
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="login-email">Email</Label>
            <Input
              id="login-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              data-testid="login-email-input"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="login-password">Password</Label>
            <Input
              id="login-password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              data-testid="login-password-input"
            />
          </div>
          <Button
            type="submit"
            className="w-full"
            disabled={signIn.isPending}
            data-testid="login-submit-button"
          >
            {signIn.isPending ? "Signing in…" : "Sign in"}
          </Button>
          <p className="text-sm text-slate-500">
            New here?{" "}
            <Link
              to="/register"
              className="font-medium text-blue-600 transition-colors duration-200 hover:text-blue-700"
              data-testid="login-register-link"
            >
              Create an account
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
