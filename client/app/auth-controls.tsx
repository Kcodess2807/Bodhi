"use client";

import { useAuth } from "@clerk/nextjs";
import { SignInButton, UserButton } from "@clerk/nextjs";

export default function AuthControls() {
  const { isSignedIn, isLoaded } = useAuth();

  if (!isLoaded) return null;

  if (isSignedIn) {
    return <UserButton />;
  }

  return (
    <SignInButton mode="modal">
      <button className="rounded bg-white px-4 py-1.5 text-sm font-medium text-black transition hover:bg-zinc-200">
        Sign In
      </button>
    </SignInButton>
  );
}
