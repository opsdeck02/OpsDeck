import { redirect } from "next/navigation";

import { DashboardShell } from "@/components/shell/dashboard-shell";
import { getCurrentUser, getPlantContextOptions } from "@/lib/api";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await getCurrentUser();

  if (!user) {
    redirect("/login");
  }

  const plantOptions = user.is_superadmin ? [] : await getPlantContextOptions();

  return (
    <DashboardShell user={user} plantOptions={plantOptions}>
      {children}
    </DashboardShell>
  );
}
