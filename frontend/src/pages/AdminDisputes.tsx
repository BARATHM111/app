import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { StatusBadge } from "@/components/Badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiGet, apiPost } from "@/lib/api";
import { extractErrorMessage, shortDate } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { ExchangeDetail, ExchangeListResponse } from "@/lib/types";

export default function AdminDisputes() {
  const { user } = useSession();
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const disputes = useQuery({
    queryKey: ["admin-disputes"],
    queryFn: () => apiGet<ExchangeListResponse>("/v1/admin/disputes"),
    enabled: user?.role === "admin",
  });
  const resolve = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "resume" | "cancel" }) =>
      apiPost<ExchangeDetail>(`/v1/admin/exchanges/${id}/resolve`, { action, note: notes[id] ?? "" }),
    onSuccess: async (data) => {
      toast.success(`Exchange ${data.exchange.status === "cancelled" ? "cancelled" : "resumed"}`);
      await queryClient.invalidateQueries({ queryKey: ["admin-disputes"] });
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not resolve the dispute")),
  });

  if (user?.role !== "admin") {
    return (
      <div className="bx-panel p-8 text-sm text-slate-500" data-testid="admin-disputes-forbidden">
        Admin access required.
      </div>
    );
  }
  const items = disputes.data?.exchanges ?? [];
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-heading text-3xl font-bold tracking-tight text-slate-900">
          Dispute <span className="text-blue-600">resolution</span> center
        </h1>
        <p className="text-sm text-slate-500">
          Resume a disputed exchange or cancel it. Cancelling releases listings. Captured PayPal payments must be refunded
          manually in the PayPal dashboard. BarterX does not hold funds in escrow.
        </p>
      </div>
      <div className="bx-panel overflow-x-auto p-2">
        <table className="w-full text-sm" data-testid="admin-disputes-table">
          <thead>
            <tr className="text-left text-xs text-slate-500">
              <th className="p-3 font-medium">Exchange</th>
              <th className="p-3 font-medium">Traders</th>
              <th className="p-3 font-medium">Status</th>
              <th className="p-3 font-medium">Updated</th>
              <th className="p-3 font-medium">Resolution</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-6 text-center text-slate-500" data-testid="admin-disputes-empty">
                  No open disputes.
                </td>
              </tr>
            ) : null}
            {items.map((item) => (
              <tr key={item.id} className="border-t border-slate-100 transition-colors duration-150 hover:bg-slate-50" data-testid={`admin-dispute-${item.id}`}>
                <td className="p-3 font-mono text-xs">
                  <Link to={`/proposal/${item.id}`} className="text-blue-600 hover:text-blue-700">{item.id}</Link>
                </td>
                <td className="p-3 text-slate-700">{item.counterparties.map((c) => c.name).join(", ")}</td>
                <td className="p-3"><StatusBadge status={item.status} /></td>
                <td className="p-3 text-slate-500">{shortDate(item.updated_at)}</td>
                <td className="p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Input className="h-8 w-48" placeholder="Note (required)" value={notes[item.id] ?? ""}
                      onChange={(e) => setNotes((n) => ({ ...n, [item.id]: e.target.value }))} data-testid={`admin-dispute-${item.id}-note`} />
                    <Button size="sm" variant="outline" className="rounded-xl" disabled={resolve.isPending || (notes[item.id] ?? "").trim().length < 3}
                      onClick={() => resolve.mutate({ id: item.id, action: "resume" })} data-testid={`admin-dispute-${item.id}-resume`}>Resume</Button>
                    <Button size="sm" variant="outline" className="rounded-xl border-red-200 text-red-600" disabled={resolve.isPending || (notes[item.id] ?? "").trim().length < 3}
                      onClick={() => resolve.mutate({ id: item.id, action: "cancel" })} data-testid={`admin-dispute-${item.id}-cancel`}>Cancel</Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
