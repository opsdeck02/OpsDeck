"use client";

import { useState } from "react";

import { logout as logoutSession } from "@/lib/client-api";

export function LogoutButton() {
  const [isSigningOut, setIsSigningOut] = useState(false);

  async function logout() {
    if (isSigningOut) return;

    setIsSigningOut(true);
    try {
      await logoutSession();
    } finally {
      window.location.replace("/login");
    }
  }

  return (
    <button
      type="button"
      onClick={logout}
      disabled={isSigningOut}
      className="rounded-full border px-4 py-2 text-xs font-semibold uppercase tracking-[0.16em]"
    >
      {isSigningOut ? "Signing out" : "Sign out"}
    </button>
  );
}
