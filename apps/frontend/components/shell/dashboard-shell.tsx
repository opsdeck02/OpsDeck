"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import type { CurrentUser, RoleName } from "@steelops/contracts";

import { LogoutButton } from "@/components/auth/logout-button";
import { OpsDeckLogo } from "@/components/brand/opsdeck-logo";
import { Badge } from "@/components/ui/badge";
import type { PlantContextOption } from "@/lib/plant-context";
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
    label: "Risk workspace",
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
    label: "Inbound continuity",
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
    label: "Reliability sources",
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
    label: "Signal trust",
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
    label: "Source health",
    roles: ["tenant_admin", "buyer_user", "logistics_user", "planner_user"],
  },
  {
    href: "/dashboard/admin",
    label: "Admin",
    roles: ["tenant_admin"],
  },
];

const superadminNavItems = [
  { href: "/dashboard/superadmin", label: "Continuity" },
  { href: "/dashboard/admin", label: "Admin" },
];

export function DashboardShell({
  user,
  plantOptions,
  children,
}: {
  user: CurrentUser;
  plantOptions: PlantContextOption[];
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const isSuperadmin = canAccessSuperadmin(user);
  const activeMembership = user.memberships[0];
  const role = activeMembership?.role;
  const selectedPlantReference = searchParams.get("plant_reference") ?? "";
  const selectedPlant = plantOptions.find(
    (option) => option.reference === selectedPlantReference,
  );
  const plantContextLabel = selectedPlant?.label ?? "All plants";
  const visibleItems = dedupeNavItems(
    isSuperadmin
      ? superadminNavItems
      : navItems.filter((item) => role && item.roles.includes(role)),
  );

  function updatePlantContext(reference: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (reference) {
      params.set("plant_reference", reference);
    } else {
      params.delete("plant_reference");
    }
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  return (
    <div className="min-h-screen overflow-x-hidden px-3 py-2.5 sm:px-4 lg:px-5">
      <div className="mx-auto flex w-full max-w-[1480px] flex-col gap-3">
        <header className="bg-white/76 flex flex-col gap-3 rounded-2xl px-3.5 py-2.5 shadow-panel ring-1 ring-slate-900/5 backdrop-blur md:flex-row md:items-center md:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <OpsDeckLogo compact />
            <div className="min-w-0">
              <p className="text-xs uppercase tracking-[0.22em] text-mutedForeground">
                {isSuperadmin
                  ? "Global administration"
                  : activeMembership?.tenant_name}
              </p>
              <h1 className="mt-1 truncate text-lg font-semibold tracking-tight">
                {isSuperadmin
                  ? "OpsDeck Superadmin Console"
                  : "Continuity intelligence"}
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
        <div className="grid min-w-0 gap-3 lg:grid-cols-[136px_minmax(0,1fr)]">
          <nav className="h-fit rounded-2xl bg-white/70 p-1.5 shadow-panel ring-1 ring-slate-900/5 backdrop-blur">
            {!isSuperadmin ? (
              <div className="mb-1.5 rounded-xl bg-slate-50 px-2.5 py-2 ring-1 ring-slate-900/5">
                <label
                  htmlFor="plant-context"
                  className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-mutedForeground"
                >
                  Plant context
                </label>
                <select
                  id="plant-context"
                  value={selectedPlantReference}
                  onChange={(event) => updatePlantContext(event.target.value)}
                  className="mt-1.5 w-full rounded-lg border bg-white px-2 py-1.5 text-xs font-semibold text-foreground"
                >
                  <option value="">All plants</option>
                  {plantOptions.map((option) => (
                    <option key={option.reference} value={option.reference}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <p className="mt-1.5 break-words text-[0.7rem] leading-4 text-mutedForeground">
                  {selectedPlant
                    ? `Viewing continuity for ${plantContextLabel}`
                    : "Viewing continuity for All plants"}
                </p>
              </div>
            ) : null}
            {visibleItems.map((item) => (
              <Link
                key={item.href}
                href={hrefWithPlantContext(item.href, selectedPlantReference)}
                className="block rounded-xl px-2.5 py-1.5 text-sm font-medium text-mutedForeground transition hover:bg-slate-100 hover:text-foreground"
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

const plantContextRoutes = new Set([
  "/dashboard",
  "/dashboard/risk-workspace",
  "/dashboard/shipments",
  "/dashboard/suppliers",
  "/dashboard/movements",
]);

function hrefWithPlantContext(href: string, plantReference: string) {
  if (!plantReference || !plantContextRoutes.has(href)) {
    return href;
  }
  const params = new URLSearchParams({ plant_reference: plantReference });
  return `${href}?${params.toString()}`;
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
