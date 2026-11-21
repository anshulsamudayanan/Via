"use client";

import { Suspense } from "react";

import { ProjectsBrowser } from "@/components/projects/projects-browser";

export default function ProjectsPage() {
  return (
    <Suspense>
      <ProjectsBrowser />
    </Suspense>
  );
}
