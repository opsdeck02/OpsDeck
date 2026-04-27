import { redirect } from "next/navigation";
import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getAllTenants, getCurrentUser } from "@/lib/api";
import { canAccessSuperadmin } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function SuperadminTenantsPage() {
  const user = await getCurrentUser();
  if (!user || !canAccessSuperadmin(user)) {
    redirect("/dashboard");
  }

  const tenants = await getAllTenants();
  const activeTenants = tenants.filter((tenant) => tenant.is_active).length;
  const cappedTenants = tenants.filter((tenant) => tenant.max_users !== null).length;
  const totalMappedUsers = tenants.reduce((total, tenant) => total + (tenant.active_user_count ?? 0), 0);

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-3xl border bg-card/90 shadow-panel">
        <div className="flex flex-col gap-6 px-6 py-8 lg:flex-row lg:items-end lg:justify-between lg:px-10">
          <div className="max-w-2xl space-y-3">
            <p className="text-xs uppercase tracking-[0.22em] text-mutedForeground">
              Superadmin workspace
            </p>
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              Manage tenant portfolio and user mapping without dropping into tenant pilot dashboards.
            </h1>
            <p className="text-sm text-mutedForeground sm:text-base">
              This console is for tenant governance only: tenant lifecycle, access limits, and tenant user mapping.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/dashboard/users"
              className="rounded-2xl bg-primary px-4 py-3 text-sm font-semibold text-primaryForeground"
            >
              Open user mapping
            </Link>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle className="text-sm font-medium text-mutedForeground">Tenants</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold tracking-tight">{tenants.length}</p>
            <p className="mt-2 text-sm text-mutedForeground">{activeTenants} active tenants</p>
          </CardContent>
        </Card>
        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle className="text-sm font-medium text-mutedForeground">Mapped users</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold tracking-tight">{totalMappedUsers}</p>
            <p className="mt-2 text-sm text-mutedForeground">Active tenant-user mappings across all tenants</p>
          </CardContent>
        </Card>
        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle className="text-sm font-medium text-mutedForeground">Usage caps</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold tracking-tight">{cappedTenants}</p>
            <p className="mt-2 text-sm text-mutedForeground">Tenants with configured user limits</p>
          </CardContent>
        </Card>
      </section>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {tenants.map((tenant) => (
          <Card key={tenant.id} className="bg-card/90 shadow-panel">
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>{tenant.name}</span>
                <span
                  className={`rounded px-2 py-1 text-xs ${
                    tenant.is_active ? "bg-muted text-accent" : "bg-card text-primary"
                  }`}
                >
                  {tenant.is_active ? "Active" : "Inactive"}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-mutedForeground">Slug:</span>
                <span>{tenant.slug}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-mutedForeground">Users:</span>
                <span>{tenant.active_user_count || 0} / {tenant.max_users || 'Unlimited'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-mutedForeground">Plan:</span>
                <span className="capitalize">{tenant.plan_tier}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-mutedForeground">Access Weeks:</span>
                <span>{tenant.access_weeks || 'Unlimited'}</span>
              </div>
              {tenant.access_expires_at && (
                <div className="flex justify-between">
                  <span className="text-mutedForeground">Expires:</span>
                  <span>{new Date(tenant.access_expires_at).toLocaleDateString()}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-mutedForeground">Created:</span>
                <span>{new Date(tenant.created_at).toLocaleDateString()}</span>
              </div>
              <div className="pt-3">
                <Link
                  href={`/dashboard/users?tenant_id=${tenant.id}`}
                  className="inline-flex rounded-2xl border px-4 py-2 text-xs font-semibold"
                >
                  Manage user mapping
                </Link>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {tenants.length === 0 && (
        <Card className="bg-card/90 shadow-panel">
          <CardContent className="py-8 text-center text-mutedForeground">
            No tenants found. Create your first tenant to get started.
          </CardContent>
        </Card>
      )}
    </div>
  );
}
