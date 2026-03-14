"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useRef } from "react";

import { upsertCurrentUser } from "../lib/api";

export default function ClerkUserSync() {
  const { isSignedIn, userId, getToken } = useAuth();
  const syncedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!isSignedIn || !userId) return;
    if (syncedRef.current === userId) return;

    syncedRef.current = userId;
    void (async () => {
      try {
        const token = await getToken();
        await upsertCurrentUser(token ?? undefined);
      } catch (error) {
        console.error("Failed to sync Clerk user", error);
        syncedRef.current = null;
      }
    })();
  }, [isSignedIn, userId]);

  return null;
}
