import type { Metadata } from "next";

import { SystemStatus } from "@/components/system-status";

export const metadata: Metadata = { title: "System status" };

export default function StatusPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
      <div>
        <h1 className="text-lg font-semibold">System status</h1>
        <p className="text-sm text-muted">
          Live checks of the services VIA depends on. Refreshes every 15 seconds.
        </p>
      </div>
      <SystemStatus />
    </div>
  );
}
