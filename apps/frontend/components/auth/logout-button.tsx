"use client";

import { logout as logoutSession } from "@/lib/client-api";

export function LogoutButton() {
  async function logout() {
    await logoutSession();
    window.location.href = "/login";
  }

  return (
    <button
      type="button"
      onClick={logout}
      className="rounded-full border px-4 py-2 text-xs font-semibold uppercase tracking-[0.16em]"
    >
      Sign out
    </button>
  );
}
