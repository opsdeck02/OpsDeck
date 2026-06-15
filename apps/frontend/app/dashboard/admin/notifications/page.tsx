import { redirect } from "next/navigation";

import { NotificationSettingsForm } from "@/components/admin/notification-settings-form";
import { getCurrentUser } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function NotificationSettingsPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  const isTenantAdmin = user.memberships[0]?.role === "tenant_admin";
  if (!isTenantAdmin && !user.is_superadmin) redirect("/dashboard");

  return (
    <div className="grid gap-4">
      <section className="rounded-2xl bg-card/90 p-6 shadow-panel ring-1 ring-slate-900/5">
        <h1 className="text-3xl font-semibold text-foreground">
          Notification Settings
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-mutedForeground">
          Configure critical continuity alerts and weekly executive digests for
          the active tenant.
        </p>
      </section>
      <NotificationSettingsForm />
    </div>
  );
}
