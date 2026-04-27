import { redirect } from "next/navigation";

import { UploadPanel } from "@/components/onboarding/upload-panel";
import { getCurrentUser } from "@/lib/api";
import { canManageOperationalWorkflow } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function OnboardingPage() {
  const user = await getCurrentUser();
  const role = user?.memberships[0]?.role;
  if (!canManageOperationalWorkflow(role)) {
    redirect("/dashboard");
  }

  return <UploadPanel />;
}
