import { redirect } from "next/navigation";

import { DashboardShell } from "@/components/shell/dashboard-shell";
import { getCurrentUser } from "@/lib/api";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await getCurrentUser();

  if (!user) {
    redirect("/login");
  }

  return <DashboardShell user={user}>{children}</DashboardShell>;
}
