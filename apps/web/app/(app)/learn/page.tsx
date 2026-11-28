"use client";

import { Suspense } from "react";

import { LearnBrowser } from "@/components/learn/learn-browser";

export default function LearnPage() {
  return (
    <Suspense>
      <LearnBrowser />
    </Suspense>
  );
}
