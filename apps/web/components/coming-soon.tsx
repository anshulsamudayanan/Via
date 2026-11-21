import { Badge, Card, CardContent } from "@via/ui";
import type { ReactNode } from "react";

/** Honest placeholder for functionality that isn't built yet. Never shows sample data. */
export function ComingSoon({ icon, title, description }: { icon: ReactNode; title: string; description: ReactNode }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-2 px-6 py-12 text-center">
        <div className="text-subtle [&_svg]:size-6">{icon}</div>
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium">{title}</p>
          <Badge tone="accent">Coming soon</Badge>
        </div>
        <div className="max-w-md text-xs text-muted">{description}</div>
      </CardContent>
    </Card>
  );
}
