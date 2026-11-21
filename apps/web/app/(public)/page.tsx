import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@via/ui";
import { Cpu, FolderKanban, Layers } from "lucide-react";
import Link from "next/link";

import { SystemStatus } from "@/components/system-status";

const capabilities = [
  {
    icon: Cpu,
    title: "KiCad ingestion",
    body: "Boards are parsed into a tool-independent model: outline, layers, nets, footprints, pads, tracks, vias and zones.",
  },
  {
    icon: Layers,
    title: "Board viewer",
    body: "Inspect the real parsed board: toggle layers, select components and read their properties.",
  },
  {
    icon: FolderKanban,
    title: "Private projects",
    body: "Designs live in projects that are private by default, with access enforced on the server.",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-8">
      <section className="max-w-2xl space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">Engineering intelligence for PCB design</h1>
        <p className="text-muted">
          VIA turns PCB design files into structured engineering data you can explore, review and build on.
        </p>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button asChild variant="primary">
            <Link href="/register">Create account</Link>
          </Button>
          <Button asChild variant="secondary">
            <Link href="/login">Sign in</Link>
          </Button>
        </div>
      </section>

      <section aria-labelledby="capabilities" className="space-y-3">
        <h2 id="capabilities" className="text-xs font-medium uppercase tracking-wide text-subtle">
          Stage 1 scope
        </h2>
        <div className="grid gap-3 md:grid-cols-3">
          {capabilities.map(({ icon: Icon, title, body }) => (
            <Card key={title}>
              <CardHeader className="border-0 pb-0">
                <div className="flex items-center gap-2">
                  <Icon className="size-4 text-accent" aria-hidden="true" />
                  <CardTitle>{title}</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <CardDescription className="text-[13px] leading-relaxed">{body}</CardDescription>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section aria-labelledby="status-heading">
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <h2 id="status-heading" className="text-sm font-medium">
                Service status
              </h2>
              <SystemStatus compact pollMs={30000} />
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link href="/status">View details</Link>
            </Button>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
