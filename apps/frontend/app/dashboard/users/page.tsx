import { redirect } from "next/navigation";

import { UserAdminPage } from "@/components/admin/user-admin-page";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getAllTenants,
  getCurrentUser,
  getSuperadminTenantUsers,
  getTenantUsers,
} from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function UsersPage({
  searchParams,
}: {
  searchParams?: { tenant_id?: string };
}) {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/login");
  }

  const activeRole = user.memberships[0]?.role;
  const isTenantAdmin = activeRole === "tenant_admin";
  const isSuperadmin = user.is_superadmin;

  if (!isTenantAdmin && !isSuperadmin) {
    redirect("/dashboard");
  }

  const tenants = isSuperadmin ? await getAllTenants() : [];
  const selectedTenantId =
    isSuperadmin && searchParams?.tenant_id
      ? Number(searchParams.tenant_id)
      : user.memberships[0]?.tenant_id;
  const users =
    isSuperadmin && selectedTenantId
      ? await getSuperadminTenantUsers(selectedTenantId)
      : await getTenantUsers();

  return (
    <div className="grid gap-5">
      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>{isSuperadmin ? "Tenant user mapping" : "User and tenant administration"}</CardTitle>
          <p className="text-sm text-mutedForeground">
            {isSuperadmin
              ? "Superadmin stays in the governance layer here: map users to tenants, create tenants, and manage tenant-level access."
              : "Tenant admins can create users within the active tenant and manage role access."}
          </p>
        </CardHeader>
      </Card>

      <UserAdminPage
        currentUser={user}
        tenants={tenants}
        selectedTenantId={selectedTenantId ?? null}
        users={users}
      />
    </div>
  );
}
