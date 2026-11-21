"use client";

import { Button, Dialog, DialogContent, DialogTrigger, EmptyState, Field, Select, Skeleton } from "@via/ui";
import { Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useApi } from "@/components/api-context";
import { useAsync } from "@/lib/use-async";

/** Dashboard shortcut: choose a project you can upload to, then go to its upload panel. */
export function UploadShortcut() {
  const client = useApi();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const projects = useAsync(
    (s) => (open ? client.projects.list({ status: "active", sort: "updated", limit: 100 }, s) : Promise.resolve(null)),
    [client, open],
  );
  const writable = (projects.data?.items ?? []).filter((p) => p.my_role !== "viewer");
  const [choice, setChoice] = useState("");
  const selected = choice || writable[0]?.id || "";

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="secondary">
          <Upload /> Upload PCB
        </Button>
      </DialogTrigger>
      <DialogContent title="Upload a PCB" description="Choose the project the board belongs to.">
        {projects.loading || !projects.data ? (
          <Skeleton className="h-8 w-full" />
        ) : writable.length === 0 ? (
          <EmptyState title="No projects you can upload to" description="Create a project first, or ask an owner for editor access." />
        ) : (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              router.push(`/projects/${selected}?tab=designs`);
            }}
          >
            <Field label="Project">
              {(p) => (
                <Select {...p} value={selected} onChange={(e) => setChoice(e.target.value)}>
                  {writable.map((pr) => (
                    <option key={pr.id} value={pr.id}>
                      {pr.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <div className="flex justify-end">
              <Button type="submit" variant="primary">
                Continue
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
