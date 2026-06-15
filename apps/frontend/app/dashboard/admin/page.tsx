import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import {
  ArrowRight,
  BellRing,
  FileClock,
  ScrollText,
  Settings2,
  UsersRound,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getCurrentUser } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  const isTenantAdmin = user.memberships[0]?.role === "tenant_admin";
  if (!isTenantAdmin && !user.is_superadmin) redirect("/dashboard");

  return (
    <div className="grid gap-4">
      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Admin</CardTitle>
          <p className="text-sm text-mutedForeground">
            Manage access and operational configuration for the active tenant.
          </p>
        </CardHeader>
      </Card>

      <div className="grid gap-3 md:grid-cols-2">
        <AdminCard
          href="/dashboard/users"
          icon={<UsersRound className="h-4 w-4" />}
          title="User & Tenant Administration"
          description="Manage tenant users, roles, and administrative access."
        />
        <AdminCard
          href="/dashboard/admin/operational-configuration"
          icon={<Settings2 className="h-4 w-4" />}
          title="Operational Configuration"
          description="Configure operational continuity thresholds and interruption impact logic."
        />
        <AdminCard
          href="/dashboard/admin/historical-validation"
          icon={<FileClock className="h-4 w-4" />}
          title="Historical Validation"
          description="Review whether OpsDeck would have detected past continuity incidents before disruption."
        />
        <AdminCard
          href="/dashboard/admin/executive-continuity-report"
          icon={<ScrollText className="h-4 w-4" />}
          title="Executive Continuity Report"
          description="Create a shareable continuity briefing for pilot and operating reviews."
        />
        <AdminCard
          href="/dashboard/admin/notifications"
          icon={<BellRing className="h-4 w-4" />}
          title="Notification Settings"
          description="Configure critical email alerts, weekly digests, recipients, and cooldowns."
        />
      </div>
    </div>
  );
}

function AdminCard({
  href,
  icon,
  title,
  description,
}: {
  href: string;
  icon: ReactNode;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="group rounded-2xl bg-card/90 shadow-panel ring-1 ring-slate-900/5 transition hover:-translate-y-0.5 hover:ring-primary/30"
    >
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="rounded-lg bg-slate-100 p-2 text-slate-700">
            {icon}
          </span>
          <CardTitle>{title}</CardTitle>
        </div>
        <ArrowRight className="mt-1 h-4 w-4 text-mutedForeground transition group-hover:translate-x-0.5 group-hover:text-primary" />
      </CardHeader>
      <CardContent>
        <p className="text-sm leading-5 text-mutedForeground">{description}</p>
      </CardContent>
    </Link>
  );
}
