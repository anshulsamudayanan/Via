"use client";

import { Card } from "@via/ui";

import { ActivityList } from "@/components/activity-list";
import { PageHeader } from "@/components/app-shell";

export default function ActivityPage() {
  return (
    <>
      <PageHeader title="Activity" description="Changes in projects you can access, and your own account events." />
      <Card>
        <ActivityList pageSize={30} />
      </Card>
    </>
  );
}
