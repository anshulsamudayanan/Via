"use client";

import { Suspense } from "react";

import { DesignsBrowser } from "@/components/designs/designs-browser";

export default function DesignsPage() {
  return (
    <Suspense>
      <DesignsBrowser />
    </Suspense>
  );
}
