import Link from "next/link";

import type { CurrentUser, RoleName } from "@steelops/contracts";

import { LogoutButton } from "@/components/auth/logout-button";
import { OpsDeckLogo } from "@/components/brand/opsdeck-logo";
import { Badge } from "@/components/ui/badge";
import { canAccessSuperadmin, formatRoleLabel } from "@/lib/roles";

const navItems: Array<{ href: string; label: string; roles: RoleName[] }> = [
  {
    href: "/dashboard",
    label: "Overview",
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
    label: "Shipments",
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
    label: "Movements",
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
    href: "/dashboard/onboarding",
    label: "Onboarding",
    roles: ["tenant_admin", "buyer_user", "logistics_user", "planner_user"],
  },
  {
    href: "/dashboard/pilot-admin",
    label: "Pilot Admin",
    roles: ["tenant_admin"],
  },
  {
    href: "/dashboard/exceptions",
    label: "Exceptions",
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
    href: "/dashboard/users",
    label: "Users",
    roles: ["tenant_admin"],
  },
];

const superadminNavItems = [
  { href: "/dashboard/superadmin", label: "Tenants" },
  { href: "/dashboard/users", label: "User Mapping" },
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
  const visibleItems = isSuperadmin
    ? superadminNavItems
    : navItems.filter((item) => role && item.roles.includes(role));

  return (
    <div className="min-h-screen overflow-x-hidden px-4 py-6 sm:px-6 lg:px-10">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <header className="flex flex-col gap-4 rounded-3xl border bg-card/90 px-5 py-4 shadow-panel backdrop-blur md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-4">
            <OpsDeckLogo compact />
            <div>
            <p className="text-xs uppercase tracking-[0.22em] text-mutedForeground">
              {isSuperadmin ? "Global administration" : activeMembership?.tenant_name}
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">
              {isSuperadmin ? "OpsDeck Superadmin Console" : "OpsDeck Control Tower"}
            </h1>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Badge variant="outline">
              {isSuperadmin ? "superadmin" : formatRoleLabel(role)}
            </Badge>
            <span className="text-sm text-mutedForeground">{user.full_name}</span>
            <LogoutButton />
          </div>
        </header>
        <div className="grid min-w-0 gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
          <nav className="h-fit rounded-3xl border bg-card/85 p-3 shadow-panel">
            {visibleItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="block rounded-2xl px-4 py-3 text-sm font-medium text-mutedForeground transition hover:bg-muted hover:text-foreground"
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
