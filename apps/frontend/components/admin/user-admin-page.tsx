"use client";

import { useEffect, useState, useTransition } from "react";

import type {
  CurrentUser,
  RoleName,
  TenantPlanSummary,
  TenantSummary,
  TenantUser,
} from "@steelops/contracts";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatRoleLabel } from "@/lib/roles";

const tenantRoles: Array<{ value: RoleName; label: string }> = [
  { value: "tenant_admin", label: "Tenant admin" },
  { value: "buyer_user", label: "Buyer" },
  { value: "logistics_user", label: "Logistics" },
  { value: "management_user", label: "Management" },
];

export function UserAdminPage({
  currentUser,
  tenants,
  selectedTenantId,
  users,
}: {
  currentUser: CurrentUser;
  tenants: TenantSummary[];
  selectedTenantId: number | null;
  users: TenantUser[];
}) {
  const isSuperadmin = currentUser.is_superadmin;
  const [tenantForm, setTenantForm] = useState({
    name: "",
    slug: "",
    plan_tier: "pilot" as "pilot" | "paid" | "enterprise",
    max_users: "",
    admin_email: "",
    admin_name: "",
    admin_password: "",
  });
  const [userForm, setUserForm] = useState({
    email: "",
    full_name: "",
    password: "",
    role: "buyer_user" as RoleName,
  });
  const [plantCount, setPlantCount] = useState("1");
  const [plantNames, setPlantNames] = useState("");
  const [tenantPlan, setTenantPlan] = useState<TenantPlanSummary | null>(null);
  const [tenantPlanEdits, setTenantPlanEdits] = useState<Record<number, "pilot" | "paid" | "enterprise">>({});
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    if (isSuperadmin) {
      return;
    }

    async function loadTenantAutomation() {
      const planResponse = await fetch("/api/tenant-plan");
      if (!planResponse.ok) {
        return;
      }
      setTenantPlan((await planResponse.json()) as TenantPlanSummary);
    }

    void loadTenantAutomation();
  }, [isSuperadmin]);

  function createTenant(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    startTransition(async () => {
      const response = await fetch("/api/tenants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: tenantForm.name,
          slug: tenantForm.slug,
          plan_tier: tenantForm.plan_tier,
          max_users: tenantForm.max_users ? Number(tenantForm.max_users) : null,
          admin_user:
            tenantForm.admin_email && tenantForm.admin_name && tenantForm.admin_password
              ? {
                  email: tenantForm.admin_email,
                  full_name: tenantForm.admin_name,
                  password: tenantForm.admin_password,
                }
              : null,
        }),
      });
      const body = (await response.json()) as { detail?: string };
      if (!response.ok) {
        setMessage(typeof body.detail === "string" ? body.detail : "Tenant creation failed.");
        return;
      }
      setMessage("Tenant created. Refreshing the page.");
      window.location.reload();
    });
  }

  function createUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    startTransition(async () => {
      const response = await fetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: userForm.email,
          full_name: userForm.full_name,
          password: userForm.password,
          role: userForm.role,
          ...(isSuperadmin && selectedTenantId ? { tenant_id: selectedTenantId } : {}),
        }),
      });
      const body = (await response.json()) as { detail?: string };
      if (!response.ok) {
        setMessage(typeof body.detail === "string" ? body.detail : "User creation failed.");
        return;
      }
      setMessage("User created. Refreshing the page.");
      window.location.reload();
    });
  }

  function deleteTenant(tenantId: number) {
    const confirmed = window.confirm("Delete this tenant and all tenant-scoped data?");
    if (!confirmed) {
      return;
    }
    setMessage(null);
    startTransition(async () => {
      const response = await fetch(`/api/tenants/${tenantId}`, { method: "DELETE" });
      if (!response.ok) {
        const body = (await response.json()) as { detail?: string };
        setMessage(typeof body.detail === "string" ? body.detail : "Tenant deletion failed.");
        return;
      }
      setMessage("Tenant deleted. Refreshing the page.");
      window.location.reload();
    });
  }

  function setTenantActivation(tenantId: number, shouldActivate: boolean) {
    setMessage(null);
    startTransition(async () => {
      const response = await fetch(
        `/api/tenants/${tenantId}/${shouldActivate ? "activate" : "deactivate"}`,
        { method: "POST" },
      );
      const body = (await response.json()) as { detail?: string };
      if (!response.ok) {
        setMessage(
          typeof body.detail === "string"
            ? body.detail
            : `Tenant ${shouldActivate ? "activation" : "deactivation"} failed.`,
        );
        return;
      }
      setMessage(`Tenant ${shouldActivate ? "activated" : "deactivated"}. Refreshing the page.`);
      window.location.reload();
    });
  }

  function configurePlants(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    startTransition(async () => {
      const response = await fetch("/api/tenants/plants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          count: Number(plantCount),
          plant_names: plantNames
            .split(/\n|,/)
            .map((name) => name.trim())
            .filter(Boolean),
        }),
      });
      const body = (await response.json()) as {
        detail?: string;
        created?: number;
        renamed?: number;
        total?: number;
      };
      if (!response.ok) {
        setMessage(typeof body.detail === "string" ? body.detail : "Plant setup failed.");
        return;
      }
      setMessage(
        `Plant setup saved. Created ${body.created ?? 0}, renamed ${body.renamed ?? 0}. Total plants: ${body.total ?? 0}.`,
      );
    });
  }

  function saveTenantPlan(tenantId: number) {
    const planTier = tenantPlanEdits[tenantId];
    if (!planTier) {
      setMessage("Select a tenant plan before saving.");
      return;
    }
    setMessage(null);
    startTransition(async () => {
      const response = await fetch(`/api/tenants/${tenantId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan_tier: planTier }),
      });
      const body = (await response.json()) as { detail?: string; plan_tier?: string };
      if (!response.ok) {
        setMessage(typeof body.detail === "string" ? body.detail : "Tenant plan update failed.");
        return;
      }
      setMessage(`Tenant plan updated to ${body.plan_tier ?? planTier}. Refreshing the page.`);
      window.location.reload();
    });
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
      <div className="space-y-5">
        {isSuperadmin ? (
          <Card className="bg-card/90 shadow-panel">
            <CardHeader>
              <CardTitle>Create tenant</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={createTenant} className="grid gap-3">
                <input
                  value={tenantForm.name}
                  onChange={(event) => setTenantForm((current) => ({ ...current, name: event.target.value }))}
                  placeholder="Tenant name"
                  className="rounded-2xl border bg-card px-4 py-3 text-sm"
                />
                <input
                  value={tenantForm.slug}
                  onChange={(event) => setTenantForm((current) => ({ ...current, slug: event.target.value }))}
                  placeholder="tenant-slug"
                  className="rounded-2xl border bg-card px-4 py-3 text-sm"
                />
                <select
                  value={tenantForm.plan_tier ?? "pilot"}
                  onChange={(event) =>
                    setTenantForm((current) => ({
                      ...current,
                      plan_tier: event.target.value as "pilot" | "paid" | "enterprise",
                    }))
                  }
                  className="rounded-2xl border bg-card px-4 py-3 text-sm"
                >
                  <option value="pilot">Pilot</option>
                  <option value="paid">Paid</option>
                  <option value="enterprise">Enterprise</option>
                </select>
                <input
                  value={tenantForm.max_users}
                  onChange={(event) => setTenantForm((current) => ({ ...current, max_users: event.target.value }))}
                  placeholder="Max users"
                  className="rounded-2xl border bg-card px-4 py-3 text-sm"
                />
                <input
                  value={tenantForm.admin_name}
                  onChange={(event) => setTenantForm((current) => ({ ...current, admin_name: event.target.value }))}
                  placeholder="Tenant admin full name"
                  className="rounded-2xl border bg-card px-4 py-3 text-sm"
                />
                <input
                  value={tenantForm.admin_email}
                  onChange={(event) => setTenantForm((current) => ({ ...current, admin_email: event.target.value }))}
                  placeholder="Tenant admin email"
                  className="rounded-2xl border bg-card px-4 py-3 text-sm"
                />
                <input
                  value={tenantForm.admin_password}
                  onChange={(event) => setTenantForm((current) => ({ ...current, admin_password: event.target.value }))}
                  placeholder="Tenant admin password"
                  className="rounded-2xl border bg-card px-4 py-3 text-sm"
                />
                <button
                  type="submit"
                  disabled={isPending}
                  className="rounded-2xl bg-primary px-4 py-3 text-sm font-semibold text-primaryForeground disabled:opacity-60"
                >
                  Create tenant
                </button>
              </form>
            </CardContent>
          </Card>
        ) : null}

        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Create tenant user</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={createUser} className="grid gap-3">
              {isSuperadmin ? (
                <p className="text-sm text-mutedForeground">
                  Target tenant: {selectedTenantId ?? "Select a tenant from the list on the right."}
                </p>
              ) : null}
              <input
                value={userForm.full_name}
                onChange={(event) => setUserForm((current) => ({ ...current, full_name: event.target.value }))}
                placeholder="Full name"
                className="rounded-2xl border bg-card px-4 py-3 text-sm"
              />
              <input
                value={userForm.email}
                onChange={(event) => setUserForm((current) => ({ ...current, email: event.target.value }))}
                placeholder="Email"
                className="rounded-2xl border bg-card px-4 py-3 text-sm"
              />
              <input
                value={userForm.password}
                onChange={(event) => setUserForm((current) => ({ ...current, password: event.target.value }))}
                placeholder="Password"
                className="rounded-2xl border bg-card px-4 py-3 text-sm"
              />
              <select
                value={userForm.role}
                onChange={(event) =>
                  setUserForm((current) => ({ ...current, role: event.target.value as RoleName }))
                }
                className="rounded-2xl border bg-card px-4 py-3 text-sm"
              >
                {tenantRoles.map((role) => (
                  <option key={role.value} value={role.value}>
                    {role.label}
                  </option>
                ))}
              </select>
              <button
                type="submit"
                disabled={isPending || (isSuperadmin && !selectedTenantId)}
                className="rounded-2xl bg-primary px-4 py-3 text-sm font-semibold text-primaryForeground disabled:opacity-60"
              >
                Create user
              </button>
            </form>
          </CardContent>
        </Card>

        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Tenant user profiles</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {users.map((user) => (
              <div key={user.id} className="rounded-2xl border bg-card p-4 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold">{user.full_name}</p>
                    <p className="text-mutedForeground">{user.email}</p>
                  </div>
                  <Badge variant="outline">{formatRoleLabel(user.role)}</Badge>
                </div>
                <p className="mt-2 text-mutedForeground">
                  Tenant: {user.tenant_name ?? currentUser.memberships[0]?.tenant_name}
                </p>
                <p className="text-mutedForeground">
                  Active: {user.is_active === false ? "No" : "Yes"}
                </p>
                <p className="text-mutedForeground">
                  Superadmin: {user.is_superadmin ? "Yes" : "No"}
                </p>
              </div>
            ))}
            {users.length === 0 ? (
              <p className="text-sm text-mutedForeground">No users found for the selected tenant.</p>
            ) : null}
          </CardContent>
        </Card>

        {message ? <p className="rounded-2xl bg-muted px-4 py-3 text-sm">{message}</p> : null}
      </div>

      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>{isSuperadmin ? "Tenant directory" : "Current tenant"}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {isSuperadmin ? (
            tenants.map((tenant) => (
              <div key={tenant.id} className="rounded-2xl border bg-card p-4 text-sm">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold">{tenant.name}</p>
                    <p className="text-mutedForeground">{tenant.slug}</p>
                  </div>
                  <Badge variant="outline">{tenant.active_user_count ?? 0} users</Badge>
                </div>
                <p className="mt-2 text-mutedForeground">
                  Max users: {tenant.max_users ?? "unlimited"}
                </p>
                <div className="mt-2 flex items-center justify-between gap-3">
                  <span className="text-mutedForeground">Plan:</span>
                  <Badge variant="outline">{tenant.plan_tier}</Badge>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <select
                    value={tenantPlanEdits[tenant.id] ?? tenant.plan_tier}
                    onChange={(event) =>
                      setTenantPlanEdits((current) => ({
                        ...current,
                        [tenant.id]: event.target.value as "pilot" | "paid" | "enterprise",
                      }))
                    }
                    className="rounded-2xl border bg-card px-3 py-2 text-xs"
                  >
                    <option value="pilot">Pilot</option>
                    <option value="paid">Paid</option>
                    <option value="enterprise">Enterprise</option>
                  </select>
                  <button
                    type="button"
                    onClick={() => saveTenantPlan(tenant.id)}
                    disabled={isPending}
                    className="rounded-2xl border px-4 py-2 text-xs font-semibold disabled:opacity-60"
                  >
                    Save plan
                  </button>
                </div>
                <div className="mt-3 flex flex-wrap gap-3">
                  <a
                    href={`/dashboard/users?tenant_id=${tenant.id}`}
                    className="rounded-2xl border px-4 py-2 text-xs font-semibold"
                  >
                    View users
                  </a>
                  <button
                    type="button"
                    onClick={() => setTenantActivation(tenant.id, !tenant.is_active)}
                    disabled={isPending}
                    className="rounded-2xl border px-4 py-2 text-xs font-semibold disabled:opacity-60"
                  >
                    {tenant.is_active ? "Deactivate tenant" : "Activate tenant"}
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteTenant(tenant.id)}
                    disabled={isPending}
                    className="rounded-2xl border border-accent px-4 py-2 text-xs font-semibold text-primary disabled:opacity-60"
                  >
                    Delete tenant
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="rounded-2xl border bg-card p-4 text-sm">
              <p className="font-semibold">{currentUser.memberships[0]?.tenant_name}</p>
              <p className="text-mutedForeground">{currentUser.memberships[0]?.tenant_slug}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Badge variant="outline">Plan: {tenantPlan?.plan_tier ?? "pilot"}</Badge>
                <Badge variant="outline">
                  Automation {tenantPlan?.capabilities?.automated_data_sources ? "enabled" : "locked"}
                </Badge>
              </div>
              <form onSubmit={configurePlants} className="mt-4 space-y-3">
                <p className="text-mutedForeground">
                  Enter the required number of plants. Names are optional. If you leave names blank,
                  uploads like `Plant A`, `Plant 1`, or `Swastik Steel Plant 1` can auto-name the
                  matching numbered plant later.
                </p>
                <input
                  value={plantCount}
                  onChange={(event) => setPlantCount(event.target.value)}
                  inputMode="numeric"
                  placeholder="Number of plants"
                  required
                  className="w-full rounded-2xl border bg-card px-4 py-3 text-sm"
                />
                <textarea
                  value={plantNames}
                  onChange={(event) => setPlantNames(event.target.value)}
                  placeholder={"Optional plant names, one per line or comma separated\nPlant Alpha\nPlant Beta"}
                  className="min-h-28 w-full rounded-2xl border bg-card px-4 py-3 text-sm"
                />
                <button
                  type="submit"
                  disabled={isPending}
                  className="rounded-2xl bg-primary px-4 py-3 text-sm font-semibold text-primaryForeground disabled:opacity-60"
                >
                  Save plant count
                </button>
              </form>
              <div className="mt-6 space-y-3 border-t pt-4">
                <p className="font-semibold">Automation setup</p>
                <div className="rounded-2xl border border-dashed px-4 py-4">
                  <p className="font-medium">Manual upload or URL-based ingestion now lives in onboarding.</p>
                  <p className="mt-2 text-mutedForeground">
                    Open the onboarding section to upload files, review forgiving column matches, and save Google Sheets or Excel Online URLs.
                  </p>
                  <a
                    href="/dashboard/onboarding"
                    className="mt-3 inline-flex rounded-2xl border px-4 py-2 text-xs font-semibold"
                  >
                    Open onboarding
                  </a>
                </div>
              </div>
            </div>
          )}
          {isSuperadmin && tenants.length === 0 ? (
            <p className="text-sm text-mutedForeground">No tenants are available yet.</p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
