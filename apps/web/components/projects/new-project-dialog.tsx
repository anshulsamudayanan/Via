"use client";

import type { Project, ProjectVisibility } from "@via/types";
import { Button, Dialog, DialogContent, DialogTrigger, ErrorState, Field, Input, Select, Textarea } from "@via/ui";
import { Plus } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";

import { useApi } from "@/components/api-context";
import { useSession } from "@/components/session";
import { errorMessage, fieldErrors } from "@/lib/errors";

interface Props {
  onCreated: (project: Project) => void;
  trigger?: ReactNode;
}

export function NewProjectDialog({ onCreated, trigger }: Props) {
  const client = useApi();
  const { me } = useSession();
  const personal = me.organizations.find((o) => o.is_personal) ?? me.organizations[0];
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [organizationId, setOrganizationId] = useState(personal?.id ?? "");
  const [visibility, setVisibility] = useState<ProjectVisibility>("private");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  function reset() {
    setName("");
    setDescription("");
    setVisibility("private");
    setOrganizationId(personal?.id ?? "");
    setErrors({});
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      setErrors({ name: "Enter a project name." });
      return;
    }
    setSubmitting(true);
    setErrors({});
    try {
      const project = await client.projects.create({
        name: name.trim(),
        description: description.trim(),
        organization_id: organizationId || undefined,
        visibility,
      });
      setOpen(false);
      reset();
      onCreated(project);
    } catch (err) {
      const fields = fieldErrors(err);
      setErrors(Object.keys(fields).length ? fields : { form: errorMessage(err) });
    } finally {
      setSubmitting(false);
    }
  }

  const selectedOrg = me.organizations.find((o) => o.id === organizationId);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>
        {trigger ?? (
          <Button variant="primary">
            <Plus /> New project
          </Button>
        )}
      </DialogTrigger>
      <DialogContent title="New project" description="Projects hold your PCB designs. They're private by default.">
        <form id="new-project" onSubmit={onSubmit} className="space-y-3" noValidate>
          {errors.form ? <ErrorState title={errors.form} /> : null}
          <Field label="Name" error={errors.name}>
            {(p) => <Input {...p} autoFocus maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />}
          </Field>
          <Field label="Description" hint="Optional." error={errors.description}>
            {(p) => <Textarea {...p} maxLength={2000} rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />}
          </Field>
          {me.organizations.length > 1 ? (
            <Field label="Organization">
              {(p) => (
                <Select {...p} value={organizationId} onChange={(e) => setOrganizationId(e.target.value)}>
                  {me.organizations.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.is_personal ? "Personal workspace" : o.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          ) : null}
          <Field
            label="Visibility"
            hint={
              visibility === "private"
                ? "Only you and people you add can see it."
                : selectedOrg?.is_personal
                  ? "Your personal workspace has no other members, so this is effectively private."
                  : "Members of the organization can view it."
            }
          >
            {(p) => (
              <Select {...p} value={visibility} onChange={(e) => setVisibility(e.target.value as ProjectVisibility)}>
                <option value="private">Private</option>
                <option value="organization">Organization</option>
              </Select>
            )}
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={submitting}>
              {submitting ? "Creating..." : "Create project"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
