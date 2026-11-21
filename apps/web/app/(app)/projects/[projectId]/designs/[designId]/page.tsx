"use client";

import { Suspense } from "react";

import { DesignView } from "@/components/designs/design-view";

export default function DesignPage() {
  return (
    <Suspense>
      <DesignView />
    </Suspense>
  );
}
