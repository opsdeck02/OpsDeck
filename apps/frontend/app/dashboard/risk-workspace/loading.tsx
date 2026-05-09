import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function RiskWorkspaceLoading() {
  return (
    <div className="grid gap-4">
      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Loading operational exposure</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-4">
            <div className="h-16 rounded-xl bg-muted" />
            <div className="h-16 rounded-xl bg-muted" />
            <div className="h-16 rounded-xl bg-muted" />
            <div className="h-16 rounded-xl bg-muted" />
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(280px,0.6fr)]">
        <div className="h-64 rounded-2xl border bg-card/90 shadow-panel" />
        <div className="h-64 rounded-2xl border bg-card/90 shadow-panel" />
      </div>
    </div>
  );
}
