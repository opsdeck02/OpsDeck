import { LoginForm } from "@/components/auth/login-form";
import { OpsDeckLogo } from "@/components/brand/opsdeck-logo";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function LoginPage() {
  return (
    <main className="grid min-h-screen place-items-center px-4 py-10">
      <Card className="w-full max-w-xl bg-card/90 shadow-panel backdrop-blur">
        <CardHeader className="space-y-4">
          <OpsDeckLogo />
          <Badge variant="outline">OpsDeck MVP</Badge>
          <div className="space-y-2">
            <CardTitle className="text-3xl tracking-tight">Sign in to the control tower</CardTitle>
            <p className="text-sm text-mutedForeground">
              Tenant demo accounts use{" "}
              <span className="font-semibold text-foreground">Password123!</span>. The seeded
              superadmin uses{" "}
              <span className="font-semibold text-foreground">SuperAdmin123!</span>.
            </p>
          </div>
        </CardHeader>
        <CardContent>
          <LoginForm />
        </CardContent>
      </Card>
    </main>
  );
}
