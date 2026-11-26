"use client";

import { Suspense } from "react";

import { AnalysisBrowser } from "@/components/analysis/analysis-browser";

export default function AnalysisPage() {
  return (
    <Suspense>
      <AnalysisBrowser />
    </Suspense>
  );
}
