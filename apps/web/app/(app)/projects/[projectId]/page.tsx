"use client";

import { Suspense } from "react";

import { ProjectWorkspace } from "@/components/projects/workspace";

export default function ProjectPage() {
  return (
    <Suspense>
      <ProjectWorkspace />
    </Suspense>
  );
}
