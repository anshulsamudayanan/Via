import { Card, CardContent } from "@via/ui";
import type { ReactNode } from "react";

export function AuthCard({ title, subtitle, children, footer }: { title: string; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        {subtitle ? <p className="text-sm text-muted">{subtitle}</p> : null}
      </div>
      <Card>
        <CardContent className="py-4">{children}</CardContent>
      </Card>
      {footer ? <div className="text-center text-sm text-muted">{footer}</div> : null}
    </div>
  );
}
