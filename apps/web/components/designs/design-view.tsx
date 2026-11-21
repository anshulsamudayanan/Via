"use client";

import { ApiError } from "@via/api-client";
import type { BoardSummary, DesignDetail, Project } from "@via/types";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  CardTitle,
  cn,
  Dialog,
  DialogContent,
  DialogTrigger,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Skeleton,
} from "@via/ui";
import { AlertTriangle, FolderX, Pencil, ScanEye, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";

import { useApi } from "@/components/api-context";
import { ComingSoon } from "@/components/coming-soon";
import { ComponentsTable, LayersTable, NetsTable } from "@/components/designs/data-tables";
import { isTerminal, RevisionStatusBadge } from "@/components/designs/revision-status";
import { UploadPanel } from "@/components/designs/upload-panel";
import { useRevisionPoll } from "@/components/designs/use-revision-poll";
import { errorMessage } from "@/lib/errors";
import { formatBytes, formatDateTime, mm } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

const TABS = [
  { id: "components", label: "Components" },
  { id: "nets", label: "Nets" },
  { id: "layers", label: "Layers" },
  { id: "revisions", label: "Revisions" },
] as const;
type Tab = (typeof TABS)[number]["id"];

export function DesignView() {
  const client = useApi();
  const { projectId, designId } = useParams<{ projectId: string; designId: string }>();
  const params = useSearchParams();
  const requestedRevision = params.get("revision") ?? undefined;
  const project = useAsync((s) => client.projects.get(projectId, s), [client, projectId]);
  const design = useAsync((s) => client.designs.get(designId, s), [client, designId]);
  const latest = design.data?.revisions[0] ?? null;
  const polled = useRevisionPoll(latest && !isTerminal(latest.status) ? latest : null);

  // When the latest upload finishes parsing, reload the design (current revision changes).
  useEffect(() => {
    if (polled && isTerminal(polled.status)) design.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [polled?.status]);

  if (design.error || project.error) {
    const err = design.error ?? project.error;
    if (err instanceof ApiError && (err.status === 404 || err.status === 422)) {
      return (
        <EmptyState
          icon={<FolderX />}
          title="Design not found"
          description="It may have been deleted, or you don't have access to it."
          action={<Button asChild size="sm"><Link href={`/projects/${projectId}?tab=designs`}>Back to designs</Link></Button>}
        />
      );
    }
    return <ErrorState title="Couldn't load this design" description={errorMessage(err)} />;
  }
  if (!design.data || !project.data) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-7 w-72" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const d = design.data;
  const p = project.data;
  const canEdit = p.my_role !== "viewer" && !p.archived_at;
  const viewedRevisionId = requestedRevision ?? d.current_revision?.id;
  const latestStatus = polled?.status ?? latest?.status;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="text-xs text-muted">
            <Link href="/projects" className="hover:text-foreground hover:underline">Projects</Link> /{" "}
            <Link href={`/projects/${p.id}?tab=designs`} className="hover:text-foreground hover:underline">{p.name}</Link> / Designs
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-lg font-semibold tracking-tight">{d.name}</h1>
            {latestStatus ? <RevisionStatusBadge status={latestStatus} /> : null}
            <Badge>{d.revision_count} revision{d.revision_count === 1 ? "" : "s"}</Badge>
          </div>
        </div>
        {canEdit ? <DesignActions design={d} project={p} onRenamed={design.setData} /> : null}
      </div>

      {latest && latest.status === "failed" && latest.id !== d.current_revision?.id ? (
        <ErrorState
          icon={<AlertTriangle />}
          title={`Revision ${latest.revision_number} failed to parse`}
          description={`${latest.error_message ?? "Unknown error"} (${latest.error_code})${d.current_revision ? ` Showing revision ${d.current_revision.revision_number}.` : ""}`}
        />
      ) : null}
      {polled && !isTerminal(polled.status) ? (
        <div role="status" className="rounded-md border border-border bg-surface-raised px-3 py-2 text-sm text-muted">
          Revision {polled.revision_number} is being parsed. This page updates automatically.
        </div>
      ) : null}

      {viewedRevisionId ? (
        <ParsedDesign design={d} revisionId={viewedRevisionId} isCurrent={viewedRevisionId === d.current_revision?.id} />
      ) : (
        <Card>
          <EmptyState
            title="No parsed revision yet"
            description={latest?.status === "failed" ? "The upload couldn't be parsed. Upload a corrected file below." : "Parsing results will appear here."}
          />
        </Card>
      )}

      {canEdit ? (
        <section aria-labelledby="new-revision" className="space-y-2">
          <h2 id="new-revision" className="text-sm font-medium">Upload a new revision</h2>
          <UploadPanel projectId={p.id} designId={d.id} onUploaded={() => design.reload()} onSettled={() => design.reload()} />
        </section>
      ) : null}
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="px-4 py-3" title={hint}>
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-0.5 font-mono text-sm tabular-nums">{value}</div>
    </div>
  );
}

function ParsedDesign({ design, revisionId, isCurrent }: { design: DesignDetail; revisionId: string; isCurrent: boolean }) {
  const client = useApi();
  const params = useSearchParams();
  const pathname = usePathname();
  const tab = (TABS.find((t) => t.id === params.get("tab"))?.id ?? "components") as Tab;
  const summary = useAsync((s) => client.pcb.summary(design.id, isCurrent ? undefined : revisionId, s), [client, design.id, revisionId, isCurrent]);

  if (summary.error) {
    return <ErrorState title="Couldn't load board information" description={errorMessage(summary.error)} />;
  }
  if (!summary.data) return <Skeleton className="h-48 w-full" />;
  const s = summary.data;
  const rev = s.revision;
  const query = (t: string) => {
    const next = new URLSearchParams(params.toString());
    next.set("tab", t);
    return `${pathname}?${next.toString()}`;
  };

  return (
    <div className="space-y-4">
      {!isCurrent ? (
        <div role="status" className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-surface-raised px-3 py-2 text-sm">
          <span>Viewing revision {rev.revision_number} (not the latest parsed revision).</span>
          <Link href={pathname} className="text-accent hover:underline">View current</Link>
        </div>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Board</CardTitle>
              {s.title ? <p className="text-xs text-muted">{s.title}</p> : null}
            </div>
            {s.geometry && !s.geometry.outline_closed ? <Badge tone="warning">Outline not closed</Badge> : null}
          </CardHeader>
          <div className="grid grid-cols-2 divide-border sm:grid-cols-4">
            <Stat label="Dimensions" value={s.stats.board_width !== null ? `${Number(s.stats.board_width.toFixed(2))} × ${Number((s.stats.board_height ?? 0).toFixed(2))} mm` : "-"} hint="Bounding box of the board outline" />
            <Stat label="Area" value={s.stats.board_area !== null ? `${Number(s.stats.board_area.toFixed(1))} mm²` : "-"} />
            <Stat label="Thickness" value={mm(s.stats.board_thickness)} />
            <Stat label="Layers" value={`${s.stats.copper_layer_count} Cu / ${s.stats.layer_count}`} />
            <Stat label="Components" value={`${s.stats.component_count}`} hint={`${s.stats.components_top} top, ${s.stats.components_bottom} bottom`} />
            <Stat label="Pads" value={`${s.stats.pad_count}`} hint={`${s.stats.smd_pad_count} SMD, ${s.stats.through_hole_pad_count} through-hole`} />
            <Stat label="Nets" value={`${s.stats.net_count}`} />
            <Stat label="Tracks / vias" value={`${s.stats.track_count} / ${s.stats.via_count}`} />
            <Stat label="Track length" value={mm(s.stats.total_track_length, 1)} />
            <Stat label="Min track width" value={mm(s.stats.min_track_width, 3)} />
            <Stat label="Min via drill" value={mm(s.stats.min_via_drill, 3)} />
            <Stat label="Zones" value={`${s.stats.zone_count}`} />
          </div>
        </Card>
        <Card>
          <CardHeader><CardTitle>Source</CardTitle></CardHeader>
          <dl className="divide-y divide-border text-sm">
            {[
              ["File", s.source.filename ?? rev.source_file?.original_filename ?? "-"],
              ["Size", rev.source_file ? formatBytes(rev.source_file.size_bytes) : "-"],
              ["Format", `KiCad ${s.source.format_version ?? ""}`.trim()],
              ["Generator", [s.source.generator, s.source.generator_version].filter(Boolean).join(" ") || "-"],
              ["Revision", `${rev.revision_number}`],
              ["Parsed", rev.imported_at ? formatDateTime(rev.imported_at) : "-"],
              ["Parser", `v${rev.parser_version} · schema ${rev.schema_version}`],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 px-4 py-1.5">
                <dt className="text-muted">{k}</dt>
                <dd className="truncate text-right" title={v}>{v}</dd>
              </div>
            ))}
            <div className="px-4 py-1.5">
              <dt className="text-muted">SHA-256</dt>
              <dd className="font-mono text-[11px] break-all text-muted">{rev.source_sha256}</dd>
            </div>
          </dl>
        </Card>
      </div>

      {s.warnings.length ? <Warnings summary={s} /> : null}

      <ComingSoon
        icon={<ScanEye />}
        title="Board viewer"
        description="An interactive view of this board (layers, components, tracks, vias, zoom and selection) is coming in the next update. It will render this parsed data, never sample layouts."
      />

      <nav aria-label="Design data" className="-mx-1 flex gap-0.5 overflow-x-auto border-b border-border px-1">
        {TABS.map((t) => (
          <Link
            key={t.id}
            href={query(t.id)}
            aria-current={tab === t.id ? "page" : undefined}
            className={cn(
              "-mb-px border-b-2 px-2.5 py-2 text-sm whitespace-nowrap",
              tab === t.id ? "border-accent font-medium text-foreground" : "border-transparent text-muted hover:text-foreground",
            )}
          >
            {t.label}
          </Link>
        ))}
      </nav>
      {tab === "components" ? <ComponentsTable designId={design.id} revisionId={isCurrent ? undefined : revisionId} /> : null}
      {tab === "nets" ? <NetsTable designId={design.id} revisionId={isCurrent ? undefined : revisionId} /> : null}
      {tab === "layers" ? <LayersTable designId={design.id} revisionId={isCurrent ? undefined : revisionId} /> : null}
      {tab === "revisions" ? <Revisions design={design} viewing={revisionId} /> : null}
    </div>
  );
}

function Warnings({ summary }: { summary: BoardSummary }) {
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Parser warnings ({summary.warnings.length})</CardTitle>
          <p className="text-xs text-muted">Things the parser skipped or found suspicious. Nothing here was guessed or filled in.</p>
        </div>
      </CardHeader>
      <ul className="divide-y divide-border text-sm">
        {summary.warnings.map((w, i) => (
          <li key={i} className="flex gap-3 px-4 py-1.5">
            <code className="shrink-0 text-xs text-warning">{w.code}</code>
            <span className="text-muted">{w.message}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Revisions({ design, viewing }: { design: DesignDetail; viewing: string }) {
  const pathname = usePathname();
  return (
    <Card>
      <ul className="divide-y divide-border">
        {design.revisions.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-3 px-4 py-2 text-sm">
            <span className="w-12 font-mono text-xs text-muted">rev {r.revision_number}</span>
            <RevisionStatusBadge status={r.status} />
            <span className="min-w-0 flex-1 truncate">{r.source_file?.original_filename ?? "-"}</span>
            <span className="text-xs text-muted">{r.created_by?.display_name ?? ""} · {formatDateTime(r.created_at)}</span>
            {r.status === "ready" ? (
              r.id === viewing ? <Badge tone="accent">Viewing</Badge> : <Link href={`${pathname}?revision=${r.id}`} className="text-xs text-accent hover:underline">View</Link>
            ) : r.status === "failed" ? (
              <span className="w-full text-xs text-danger">{r.error_message} ({r.error_code})</span>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function DesignActions({ design, project, onRenamed }: { design: DesignDetail; project: Project; onRenamed: (d: DesignDetail) => void }) {
  const client = useApi();
  const router = useRouter();
  const [name, setName] = useState(design.name);
  const [renameOpen, setRenameOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function rename() {
    setBusy(true);
    setError(null);
    try {
      onRenamed(await client.designs.update(design.id, { name: name.trim() }));
      setRenameOpen(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await client.designs.delete(design.id);
      router.replace(`/projects/${project.id}?tab=designs`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="flex gap-2">
      <Dialog open={renameOpen} onOpenChange={(o) => { setRenameOpen(o); setName(design.name); setError(null); }}>
        <DialogTrigger asChild>
          <Button size="sm"><Pencil /> Rename</Button>
        </DialogTrigger>
        <DialogContent title="Rename design">
          <form onSubmit={(e) => { e.preventDefault(); void rename(); }} className="space-y-3">
            {error ? <ErrorState title={error} /> : null}
            <Field label="Name">{(p) => <Input {...p} autoFocus maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
            <div className="flex justify-end">
              <Button type="submit" variant="primary" disabled={busy || !name.trim() || name === design.name}>Save</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog>
        <DialogTrigger asChild>
          <Button size="sm" variant="ghost" aria-label="Delete design"><Trash2 /></Button>
        </DialogTrigger>
        <DialogContent title="Delete design" description={`This deletes "${design.name}", all ${design.revision_count} revision(s), parsed data and stored files.`}>
          {error ? <ErrorState className="mb-3" title={error} /> : null}
          <div className="flex justify-end">
            <Button variant="danger" disabled={busy} onClick={() => void remove()}>{busy ? "Deleting..." : "Delete design"}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
