// Session ownership: the JWT lives in an httpOnly cookie the browser sends automatically,
// so the frontend never sees or stores a token. `endSession` clears the whole react-query
// cache so one trader's data can never render for the next login on this browser.

import { useQuery } from "@tanstack/react-query";

import { apiGet, apiPost } from "@/lib/api";
import { queryClient } from "@/lib/queryClient";
import type { MessageResponse, SessionResponse, UserMe } from "@/lib/types";

export const SESSION_QUERY_KEY = ["session"] as const;

/** Resolves to null when signed out (or when no backend is reachable) — never throws. */
export async function fetchSession(): Promise<UserMe | null> {
  try {
    return (await apiGet<SessionResponse>("/v1/auth/session")).user;
  } catch {
    return null;
  }
}

export function useSession() {
  const query = useQuery({
    queryKey: SESSION_QUERY_KEY,
    queryFn: fetchSession,
    retry: false,
    staleTime: 30_000,
  });
  return { user: query.data ?? null, isLoading: query.isLoading, refetch: query.refetch };
}

/** Call after a successful login or signup. */
export async function beginSession(): Promise<void> {
  await queryClient.invalidateQueries();
}

/** The only sign-out path: clears the cookie server-side, then the local cache. */
export async function endSession(): Promise<void> {
  try {
    await apiPost<MessageResponse>("/v1/auth/logout");
  } finally {
    queryClient.clear();
    await queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY });
  }
}
