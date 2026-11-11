import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, CheckCheck } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiGet, apiPost } from "@/lib/api";
import { dateTime, extractErrorMessage } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { MessageResponse, Notification, NotificationPage } from "@/lib/types";

export default function Notifications() {
  const { user, isLoading } = useSession();
  const queryClient = useQueryClient();

  const notifications = useQuery({
    queryKey: ["notifications", "list"],
    queryFn: () => apiGet<NotificationPage>("/v1/notifications?page_size=50"),
    enabled: Boolean(user),
    retry: false,
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["notifications"] });
  };

  const markRead = useMutation({
    mutationFn: (id: string) => apiPost<Notification>(`/v1/notifications/${id}/read`),
    onSuccess: invalidate,
    onError: (error) => toast.error(extractErrorMessage(error, "Could not mark that as read")),
  });

  const markAll = useMutation({
    mutationFn: () => apiPost<MessageResponse>("/v1/notifications/read-all"),
    onSuccess: async (result) => {
      await invalidate();
      toast.success(result.message);
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not mark everything as read")),
  });

  if (isLoading) {
    return <div className="h-64 rounded-2xl border border-slate-200 bg-white bx-shimmer" />;
  }

  if (!user) {
    return (
      <div className="bx-panel mx-auto max-w-xl space-y-4 p-8 text-center" data-testid="notifications-signin-prompt">
        <h1 className="font-heading text-2xl text-slate-900">Sign in to see your notifications</h1>
        <Link
          to="/login"
          className="inline-flex rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-blue-600"
          data-testid="notifications-signin-link"
        >
          Sign in
        </Link>
      </div>
    );
  }

  const items = notifications.data?.items ?? [];

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-2">
          <h1 className="font-heading text-3xl font-semibold text-slate-900">Notifications</h1>
          <p className="text-slate-500">
            Approvals, proposal changes, payment verification and fulfilment — everything that moved.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => markAll.mutate()}
          disabled={markAll.isPending || items.every((item) => item.read)}
          data-testid="notifications-mark-all-button"
        >
          <CheckCheck className="size-4" aria-hidden />
          Mark all as read
        </Button>
      </div>

      {notifications.isError ? (
        <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700" data-testid="notifications-error">
          Notifications could not be loaded right now.
        </p>
      ) : null}

      {!notifications.isLoading && items.length === 0 ? (
        <div className="bx-panel flex items-center gap-3 p-8 text-slate-500" data-testid="notifications-empty-state">
          <BellRing className="size-5 text-slate-500" aria-hidden />
          Nothing yet. Propose or approve an exchange and the activity shows up here.
        </div>
      ) : null}

      <ul className="space-y-3" data-testid="notifications-list">
        {items.map((notification) => (
          <li
            key={notification.id}
            className={`rounded-2xl border p-5 backdrop-blur-xl transition-colors duration-200 ${
              notification.read
                ? "border-slate-200 bg-white"
                : "border-blue-300 bg-white"
            }`}
            data-testid={`notification-item-${notification.id}`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-1.5">
                <p className="font-mono text-[11px] uppercase tracking-wide text-slate-500">
                  {notification.type} · {dateTime(notification.created_at)}
                </p>
                <p className="font-medium text-slate-900" data-testid={`notification-item-${notification.id}-title`}>
                  {notification.title}
                </p>
                {notification.body ? <p className="text-sm text-slate-500">{notification.body}</p> : null}
                {notification.link ? (
                  <Link
                    to={notification.link}
                    className="inline-flex text-sm font-medium text-blue-600 transition-colors duration-200 hover:text-blue-700"
                    data-testid={`notification-item-${notification.id}-link`}
                  >
                    Open →
                  </Link>
                ) : null}
              </div>
              {!notification.read ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => markRead.mutate(notification.id)}
                  disabled={markRead.isPending}
                  data-testid={`notification-item-${notification.id}-read-button`}
                >
                  Mark read
                </Button>
              ) : (
                <span className="font-mono text-[11px] text-slate-400">read</span>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
