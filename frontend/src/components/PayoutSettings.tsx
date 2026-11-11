import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Wallet } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiPatch } from "@/lib/api";
import { extractErrorMessage } from "@/lib/format";
import { SESSION_QUERY_KEY } from "@/lib/session";
import type { UserMe } from "@/lib/types";

/** Where balancing payouts go. Blank means payouts use the login email. */
export default function PayoutSettings({ user }: { user: UserMe }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState(user.paypal_email ?? "");

  const save = useMutation({
    mutationFn: (value: string) => apiPatch<UserMe>("/v1/users/me", { paypal_email: value }),
    onSuccess: async (updated) => {
      setEmail(updated.paypal_email ?? "");
      await queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY });
      toast.success(updated.paypal_email ? "Payout email saved" : "Payouts will go to your login email");
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not save the payout email")),
  });

  const effective = user.paypal_email || user.email;

  return (
    <section className="bx-panel p-6" data-testid="payout-settings">
      <div className="flex items-start gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-green-50 text-green-600">
          <Wallet className="size-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1 space-y-3">
          <div>
            <h2 className="font-heading text-lg text-slate-900">Payout email</h2>
            <p className="text-sm text-slate-500">
              When you are owed money in a cycle, PayPal Sandbox sends it here automatically once the exchange
              completes. Payouts currently go to{" "}
              <span className="text-slate-900" data-testid="payout-settings-effective-email">
                {effective}
              </span>
              {user.paypal_email ? "" : " (your login email)"}.
            </p>
          </div>
          <form
            className="flex flex-col gap-2 sm:flex-row sm:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate(email.trim());
            }}
          >
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="payout-email">PayPal email</Label>
              <Input
                id="payout-email"
                type="email"
                placeholder={user.email}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                data-testid="payout-settings-email-input"
              />
            </div>
            <Button type="submit" disabled={save.isPending} data-testid="payout-settings-save-button">
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </form>
        </div>
      </div>
    </section>
  );
}
