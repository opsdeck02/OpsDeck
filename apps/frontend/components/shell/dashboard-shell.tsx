import Link from "next/link";

import type { CurrentUser, RoleName } from "@steelops/contracts";

import { LogoutButton } from "@/components/auth/logout-button";
import { OpsDeckLogo } from "@/components/brand/opsdeck-logo";
import { Badge } from "@/components/ui/badge";
import { canAccessSuperadmin, formatRoleLabel } from "@/lib/roles";

const navItems: Array<{ href: string; label: string; roles: RoleName[] }> = [
  {
    href: "/dashboard",
    label: "Continuity",
    roles: [
      "tenant_admin",
      "buyer_user",
      "logistics_user",
      "planner_user",
      "management_user",
      "sponsor_user",
    ],
  },
  {
    href: "/dashboard/risk-workspace",
    label: "Risk Workspace",
    roles: [
      "tenant_admin",
      "buyer_user",
      "logistics_user",
      "planner_user",
      "management_user",
      "sponsor_user",
    ],
  },
  {
    href: "/dashboard/shipments",
    label: "Inbound",
    roles: [
      "tenant_admin",
      "buyer_user",
      "logistics_user",
      "planner_user",
      "management_user",
      "sponsor_user",
    ],
  },
  {
    href: "/dashboard/suppliers",
    label: "Suppliers",
    roles: [
      "tenant_admin",
      "buyer_user",
      "logistics_user",
      "planner_user",
      "management_user",
      "sponsor_user",
    ],
  },
  {
    href: "/dashboard/movements",
    label: "Signals",
    roles: [
      "tenant_admin",
      "buyer_user",
      "logistics_user",
      "planner_user",
      "management_user",
      "sponsor_user",
    ],
  },
  {
    href: "/dashboard/onboarding",
    label: "Admin",
    roles: ["tenant_admin", "buyer_user", "logistics_user", "planner_user"],
  },
  {
    href: "/dashboard/users",
    label: "Admin",
    roles: ["tenant_admin"],
  },
];

const superadminNavItems = [
  { href: "/dashboard/superadmin", label: "Continuity" },
  { href: "/dashboard/users", label: "Admin" },
];

export function DashboardShell({
  user,
  children,
}: {
  user: CurrentUser;
  children: React.ReactNode;
}) {
  const isSuperadmin = canAccessSuperadmin(user);
  const activeMembership = user.memberships[0];
  const role = activeMembership?.role;
  const visibleItems = dedupeNavItems(isSuperadmin
    ? superadminNavItems
    : navItems.filter((item) => role && item.roles.includes(role)));

  return (
    <div className="min-h-screen overflow-x-hidden px-3 py-4 sm:px-5 lg:px-6">
      <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-4">
        <header className="flex flex-col gap-3 rounded-2xl border bg-card/90 px-4 py-3 shadow-panel backdrop-blur md:flex-row md:items-center md:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <OpsDeckLogo compact />
            <div className="min-w-0">
              <p className="text-xs uppercase tracking-[0.22em] text-mutedForeground">
                {isSuperadmin
                  ? "Global administration"
                  : activeMembership?.tenant_name}
              </p>
              <h1 className="mt-1 truncate text-xl font-semibold tracking-tight">
                {isSuperadmin
                  ? "OpsDeck Superadmin Console"
                  : "OpsDeck Continuity"}
              </h1>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Badge variant="outline">
              {isSuperadmin ? "superadmin" : formatRoleLabel(role)}
            </Badge>
            <span className="text-sm text-mutedForeground">
              {user.full_name}
            </span>
            <LogoutButton />
          </div>
        </header>
        <div className="grid min-w-0 gap-4 lg:grid-cols-[168px_minmax(0,1fr)]">
          <nav className="h-fit rounded-2xl border bg-card/85 p-2 shadow-panel">
            {visibleItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="block rounded-xl px-3 py-2.5 text-sm font-medium text-mutedForeground transition hover:bg-muted hover:text-foreground"
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="min-w-0">{children}</div>
        </div>
      </div>
    </div>
  );
}

function dedupeNavItems<T extends { href: string; label: string }>(items: T[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = item.label;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
