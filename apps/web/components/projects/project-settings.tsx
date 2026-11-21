"use client";

import type { Project, ProjectMember, ProjectRole, ProjectVisibility } from "@via/types";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Dialog,
  DialogContent,
  DialogTrigger,
  ErrorState,
  Field,
  Input,
  Select,
  Skeleton,
  Textarea,
} from "@via/ui";
import { Archive, ArchiveRestore, Trash2, UserMinus } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { useApi } from "@/components/api-context";
import { RoleBadge } from "@/components/projects/badges";
import { useSession } from "@/components/session";
import { errorMessage, fieldErrors } from "@/lib/errors";
import { useAsync } from "@/lib/use-async";

interface Props {
  project: Project;
  onChange: (project: Project) => void;
}

export function ProjectSettings({ project, onChange }: Props) {
  const isOwner = project.my_role === "owner";
  const canEdit = project.my_role !== "viewer" && !project.archived_at;
  return (
    <div className="max-w-3xl space-y-4">
      <GeneralSettings project={project} onChange={onChange} canEdit={canEdit} />
      <VisibilitySettings project={project} onChange={onChange} canEdit={isOwner && !project.archived_at} />
      <Members project={project} />
      {isOwner ? <DangerZone project={project} onChange={onChange} /> : null}
    </div>
  );
}

function GeneralSettings({ project, onChange, canEdit }: Props & { canEdit: boolean }) {
  const client = useApi();
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const dirty = name !== project.name || description !== project.description;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return setErrors({ name: "Enter a project name." });
    setSaving(true);
    setErrors({});
    setSaved(false);
    try {
      const updated = await client.projects.update(project.id, { name: name.trim(), description: description.trim() });
      onChange(updated);
      setName(updated.name);
      setDescription(updated.description);
      setSaved(true);
    } catch (err) {
      const fields = fieldErrors(err);
      setErrors(Object.keys(fields).length ? fields : { form: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>General</CardTitle>
          <CardDescription>{canEdit ? "Rename the project or edit its description." : "Only editors and the owner can change these."}</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-3" noValidate>
          {errors.form ? <ErrorState title={errors.form} /> : null}
          <Field label="Project name" error={errors.name}>
            {(p) => <Input {...p} disabled={!canEdit} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />}
          </Field>
          <Field label="Description" error={errors.description}>
            {(p) => <Textarea {...p} disabled={!canEdit} rows={4} maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} />}
          </Field>
          {canEdit ? (
            <div className="flex items-center justify-end gap-3">
              {saved && !dirty ? (
                <span role="status" className="text-xs text-success">
                  Saved
                </span>
              ) : null}
              <Button type="submit" variant="primary" disabled={!dirty || saving}>
                {saving ? "Saving..." : "Save changes"}
              </Button>
            </div>
          ) : null}
        </form>
      </CardContent>
    </Card>
  );
}

function VisibilitySettings({ project, onChange, canEdit }: Props & { canEdit: boolean }) {
  const client = useApi();
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function change(visibility: ProjectVisibility) {
    setSaving(true);
    setError(null);
    try {
      onChange(await client.projects.update(project.id, { visibility }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Visibility</CardTitle>
          <CardDescription>Organization membership never grants access to private projects.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {error ? <ErrorState title={error} /> : null}
        <Field
          label="Who can see this project"
          hint={
            project.visibility === "private"
              ? "Only the owner and the members listed below."
              : `Members of ${project.organization.is_personal ? "your personal workspace" : project.organization.name} can view it, plus the members listed below.`
          }
        >
          {(p) => (
            <Select {...p} className="max-w-xs" disabled={!canEdit || saving} value={project.visibility} onChange={(e) => void change(e.target.value as ProjectVisibility)}>
              <option value="private">Private</option>
              <option value="organization">Organization</option>
            </Select>
          )}
        </Field>
      </CardContent>
    </Card>
  );
}

function Members({ project }: { project: Project }) {
  const client = useApi();
  const router = useRouter();
  const { me } = useSession();
  const members = useAsync(() => client.projects.members(project.id), [client, project.id]);
  const isOwner = project.my_role === "owner";
  const editable = isOwner && !project.archived_at;
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Exclude<ProjectRole, "owner">>("viewer");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      members.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function add(event: FormEvent) {
    event.preventDefault();
    if (!email.trim()) return;
    await run(async () => {
      await client.projects.addMember(project.id, email.trim(), role);
      setEmail("");
    });
  }

  async function leave() {
    setBusy(true);
    try {
      await client.projects.removeMember(project.id, me.user.id);
      router.replace("/projects");
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  const list: ProjectMember[] = members.data ?? [];
  const iAmMember = list.some((m) => m.user.id === me.user.id);

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Members</CardTitle>
          <CardDescription>People with explicit access to this project.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {error ? <ErrorState title={error} /> : null}
        {members.loading && !members.data ? (
          <Skeleton className="h-16 w-full" />
        ) : (
          <ul className="divide-y divide-border rounded-md border border-border">
            {list.map((m) => (
              <li key={m.user.id} className="flex items-center gap-3 px-3 py-2 text-sm">
                <span className="min-w-0 flex-1 truncate">
                  {m.user.display_name}
                  {m.user.id === me.user.id ? <span className="text-muted"> (you)</span> : null}
                </span>
                {editable && m.role !== "owner" ? (
                  <>
                    <Select
                      aria-label={`Role for ${m.user.display_name}`}
                      className="h-7 w-auto text-xs"
                      disabled={busy}
                      value={m.role}
                      onChange={(e) => void run(() => client.projects.updateMember(project.id, m.user.id, e.target.value as "editor" | "viewer"))}
                    >
                      <option value="editor">Editor</option>
                      <option value="viewer">Viewer</option>
                    </Select>
                    <Button
                      size="icon"
                      variant="ghost"
                      disabled={busy}
                      aria-label={`Remove ${m.user.display_name}`}
                      onClick={() => void run(() => client.projects.removeMember(project.id, m.user.id))}
                    >
                      <UserMinus />
                    </Button>
                  </>
                ) : (
                  <RoleBadge role={m.role} />
                )}
              </li>
            ))}
          </ul>
        )}
        {editable ? (
          <form onSubmit={add} className="flex flex-wrap items-end gap-2" noValidate>
            <Field label="Add a member by email" className="min-w-56 flex-1" hint="They need an existing VIA account.">
              {(p) => <Input {...p} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />}
            </Field>
            <Select aria-label="Role for new member" className="mb-5 w-auto" value={role} onChange={(e) => setRole(e.target.value as "editor" | "viewer")}>
              <option value="viewer">Viewer</option>
              <option value="editor">Editor</option>
            </Select>
            <Button type="submit" className="mb-5" disabled={busy || !email.trim()}>
              Add
            </Button>
          </form>
        ) : !isOwner && iAmMember ? (
          <div className="flex justify-end">
            <Button size="sm" variant="ghost" onClick={() => void leave()} disabled={busy}>
              Leave project
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function DangerZone({ project, onChange }: Props) {
  const client = useApi();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmName, setConfirmName] = useState("");

  async function toggleArchive() {
    setBusy(true);
    setError(null);
    try {
      onChange(project.archived_at ? await client.projects.unarchive(project.id) : await client.projects.archive(project.id));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await client.projects.delete(project.id);
      router.replace("/projects");
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <Card className="border-danger/40">
      <CardHeader className="border-danger/30">
        <CardTitle>Danger zone</CardTitle>
      </CardHeader>
      <CardContent className="divide-y divide-border p-0">
        {error ? <ErrorState className="m-3" title={error} /> : null}
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <p className="text-sm font-medium">{project.archived_at ? "Restore project" : "Archive project"}</p>
            <p className="text-xs text-muted">
              {project.archived_at ? "Make the project editable again." : "Hide it from the active list and make it read-only. You can restore it later."}
            </p>
          </div>
          <Button variant="secondary" onClick={() => void toggleArchive()} disabled={busy}>
            {project.archived_at ? <ArchiveRestore /> : <Archive />}
            {project.archived_at ? "Restore" : "Archive"}
          </Button>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <p className="text-sm font-medium">Delete project</p>
            <p className="text-xs text-muted">Permanently delete the project and everything in it. This can&apos;t be undone.</p>
          </div>
          <Dialog onOpenChange={() => setConfirmName("")}>
            <DialogTrigger asChild>
              <Button variant="danger">
                <Trash2 /> Delete
              </Button>
            </DialogTrigger>
            <DialogContent title="Delete project" description="This permanently deletes the project, its designs and its files.">
              <div className="space-y-3">
                <Field label={`Type "${project.name}" to confirm`}>
                  {(p) => <Input {...p} autoComplete="off" value={confirmName} onChange={(e) => setConfirmName(e.target.value)} />}
                </Field>
                <div className="flex justify-end">
                  <Button variant="danger" disabled={busy || confirmName !== project.name} onClick={() => void remove()}>
                    {busy ? "Deleting..." : "Delete permanently"}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </CardContent>
    </Card>
  );
}
