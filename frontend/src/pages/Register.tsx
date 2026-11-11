import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiPost } from "@/lib/api";
import { extractErrorMessage } from "@/lib/format";
import { beginSession } from "@/lib/session";
import type { UserMe } from "@/lib/types";

export default function Register() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    location: "",
    skills: "",
    bio: "",
  });

  const register = useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiPost<UserMe>("/v1/auth/register", payload),
    onSuccess: async (user) => {
      await beginSession();
      toast.success(`Account created for ${user.name}`);
      navigate("/dashboard");
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not create your account")),
  });

  const update = (key: keyof typeof form) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  return (
    <div className="grid gap-10 lg:grid-cols-12 lg:items-start">
      <div className="space-y-5 lg:col-span-5">
        <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1 font-mono text-xs uppercase tracking-wide text-slate-500">
          Create an account
        </span>
        <h1 className="font-heading text-3xl font-semibold text-slate-900 sm:text-4xl">
          Two listings and a want is enough to start a cycle.
        </h1>
        <p className="text-slate-500">
          List physical goods or the professional service you sell. BarterX keeps ownership, values and
          approvals separate — so nothing is ever traded twice by accident.
        </p>
        <ul className="space-y-2 text-sm text-slate-700">
          <li>Multiple listings and wants per trader</li>
          <li>Explicit currency on every value</li>
          <li>Approvals recorded per revision, never assumed</li>
        </ul>
      </div>

      <div className="bx-panel p-6 lg:col-span-7 sm:p-8">
        <form
          className="grid gap-5 sm:grid-cols-2"
          data-testid="register-form"
          onSubmit={(event) => {
            event.preventDefault();
            register.mutate({
              name: form.name,
              email: form.email,
              password: form.password,
              location: form.location,
              bio: form.bio,
              skills: form.skills
                .split(",")
                .map((skill) => skill.trim())
                .filter(Boolean),
            });
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="register-name">Name</Label>
            <Input
              id="register-name"
              required
              minLength={2}
              value={form.name}
              onChange={(event) => update("name")(event.target.value)}
              placeholder="Alex Rivera"
              data-testid="register-name-input"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="register-email">Email</Label>
            <Input
              id="register-email"
              type="email"
              required
              value={form.email}
              onChange={(event) => update("email")(event.target.value)}
              placeholder="you@example.com"
              data-testid="register-email-input"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="register-password">Password</Label>
            <Input
              id="register-password"
              type="password"
              required
              minLength={8}
              value={form.password}
              onChange={(event) => update("password")(event.target.value)}
              placeholder="At least 8 characters"
              data-testid="register-password-input"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="register-location">Location</Label>
            <Input
              id="register-location"
              value={form.location}
              onChange={(event) => update("location")(event.target.value)}
              placeholder="City or Remote"
              data-testid="register-location-input"
            />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="register-skills">Skills (comma separated)</Label>
            <Input
              id="register-skills"
              value={form.skills}
              onChange={(event) => update("skills")(event.target.value)}
              placeholder="Woodworking, Photography"
              data-testid="register-skills-input"
            />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="register-bio">About you</Label>
            <Textarea
              id="register-bio"
              rows={3}
              value={form.bio}
              onChange={(event) => update("bio")(event.target.value)}
              placeholder="What you make, what you are looking for."
              data-testid="register-bio-input"
            />
          </div>
          <div className="sm:col-span-2">
            <Button
              type="submit"
              className="w-full"
              disabled={register.isPending}
              data-testid="register-submit-button"
            >
              {register.isPending ? "Creating account…" : "Create account"}
            </Button>
            <p className="mt-3 text-sm text-slate-500">
              Already trading?{" "}
              <Link
                to="/login"
                className="font-medium text-blue-600 transition-colors duration-200 hover:text-blue-700"
                data-testid="register-login-link"
              >
                Sign in
              </Link>
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}
