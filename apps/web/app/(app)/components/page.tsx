"use client";

import { Suspense } from "react";

import { PartsBrowser } from "@/components/designs/parts-browser";

export default function ComponentsPage() {
  return (
    <Suspense>
      <PartsBrowser />
    </Suspense>
  );
}
