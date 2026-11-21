"use client";

import { ApiError } from "@via/api-client";
import type { ImportResponse, Revision, UploadLimits } from "@via/types";
import { Button, Card, CardContent, cn, ErrorState, Spinner } from "@via/ui";
import { CheckCircle2, FileUp, UploadCloud, X } from "lucide-react";
import Link from "next/link";
import { type DragEvent, useEffect, useRef, useState } from "react";

import { useApi } from "@/components/api-context";
import { RevisionStatusBadge } from "@/components/designs/revision-status";
import { useRevisionPoll } from "@/components/designs/use-revision-poll";
import { errorMessage } from "@/lib/errors";
import { formatBytes } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

interface Props {
  projectId: string;
  /** Upload as a new revision of this design. */
  designId?: string;
  onUploaded?: (result: ImportResponse) => void;
  /** Called once parsing finishes, successfully or not. */
  onSettled?: (revision: Revision) => void;
}

type Stage =
  | { kind: "idle" }
  | { kind: "uploading"; file: File; loaded: number; total: number }
  | { kind: "processing"; file: File; result: ImportResponse }
  | { kind: "error"; file?: File; message: string; duplicateOf?: { designId: string; name: string } };

/** Client-side checks mirroring the API (which re-validates everything). */
export function validateFile(file: File, limits: UploadLimits): string | null {
  const exts = limits.formats.flatMap((f) => f.extensions);
  const lower = file.name.toLowerCase();
  if (!exts.some((ext) => lower.endsWith(ext))) return `Unsupported file type. Upload a ${exts.join(" or ")} file.`;
  if (file.size === 0) return "The file is empty.";
  if (file.size > limits.max_upload_bytes) {
    return `The file is ${formatBytes(file.size)}; the limit is ${formatBytes(limits.max_upload_bytes)}.`;
  }
  return null;
}

export function UploadPanel({ projectId, designId, onUploaded, onSettled }: Props) {
  const client = useApi();
  const limits = useAsync(() => client.pcb.limits(), [client]);
  const [stage, setStage] = useState<Stage>({ kind: "idle" });
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const processingRevision = stage.kind === "processing" ? stage.result.revision : null;
  const revision = useRevisionPoll(processingRevision);

  useEffect(() => {
    if (revision && (revision.status === "ready" || revision.status === "failed")) onSettled?.(revision);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- notify once per status change
  }, [revision?.id, revision?.status]);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function start(file: File) {
    // A file can be dropped before the limits have loaded: fetch them rather than ignore the file.
    let lim = limits.data;
    if (!lim) {
      try {
        lim = await client.pcb.limits();
      } catch (err) {
        setStage({ kind: "error", file, message: errorMessage(err) });
        return;
      }
    }
    const problem = validateFile(file, lim);
    if (problem) {
      setStage({ kind: "error", file, message: problem });
      return;
    }
    const ac = new AbortController();
    abortRef.current = ac;
    setStage({ kind: "uploading", file, loaded: 0, total: file.size });
    try {
      const result = await client.pcb.upload({
        projectId,
        designId,
        file,
        signal: ac.signal,
        onProgress: (loaded, total) => setStage({ kind: "uploading", file, loaded, total }),
      });
      setStage({ kind: "processing", file, result });
      onUploaded?.(result);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setStage({ kind: "idle" });
        return;
      }
      const dup =
        err instanceof ApiError && err.code === "duplicate_file" && err.details && typeof err.details === "object"
          ? (err.details as { design_id?: string; design_name?: string })
          : null;
      setStage({
        kind: "error",
        file,
        message: errorMessage(err),
        duplicateOf: dup?.design_id ? { designId: dup.design_id, name: dup.design_name ?? "design" } : undefined,
      });
    } finally {
      abortRef.current = null;
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && stage.kind !== "uploading") void start(file);
  }

  const busy = stage.kind === "uploading";
  const accept = limits.data?.formats.flatMap((f) => f.extensions).join(",") ?? ".kicad_pcb";

  return (
    <Card>
      <CardContent className="space-y-3">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            if (!busy) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            "flex flex-col items-center gap-2 rounded-md border border-dashed px-4 py-6 text-center transition-colors",
            dragging ? "border-accent bg-accent-soft" : "border-border-strong",
          )}
        >
          <UploadCloud className="size-6 text-subtle" aria-hidden="true" />
          <p className="text-sm">
            {designId ? "Drop a new revision here" : "Drop a KiCad board file here"}, or{" "}
            <button
              type="button"
              className="text-accent hover:underline disabled:opacity-50"
              disabled={busy || !limits.data}
              onClick={() => inputRef.current?.click()}
            >
              choose a file
            </button>
          </p>
          <p className="text-xs text-muted">
            {limits.data
              ? `${limits.data.formats.map((f) => `${f.name} (${f.extensions.join(", ")})`).join(", ")} · up to ${formatBytes(limits.data.max_upload_bytes)}`
              : "Loading upload limits..."}
          </p>
          <input
            ref={inputRef}
            type="file"
            accept={accept}
            className="sr-only"
            aria-label="Choose a PCB file"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void start(file);
            }}
          />
        </div>

        {stage.kind === "uploading" ? (
          <div className="space-y-1.5" aria-live="polite">
            <div className="flex items-center gap-2 text-sm">
              <FileUp className="size-4 text-subtle" aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate">{stage.file.name}</span>
              <span className="font-mono text-xs text-muted tabular-nums">
                {formatBytes(stage.loaded)} / {formatBytes(stage.total)}
              </span>
              <Button size="sm" variant="ghost" onClick={() => abortRef.current?.abort()} aria-label="Cancel upload">
                <X /> Cancel
              </Button>
            </div>
            <div
              role="progressbar"
              aria-label="Upload progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round((stage.loaded / Math.max(stage.total, 1)) * 100)}
              className="h-1.5 overflow-hidden rounded-full bg-surface-hover"
            >
              <div className="h-full bg-accent transition-[width]" style={{ width: `${(stage.loaded / Math.max(stage.total, 1)) * 100}%` }} />
            </div>
          </div>
        ) : null}

        {stage.kind === "processing" && revision ? (
          <div className="space-y-2 rounded-md border border-border px-3 py-2 text-sm" aria-live="polite">
            <div className="flex flex-wrap items-center gap-2">
              {revision.status === "ready" ? (
                <CheckCircle2 className="size-4 text-success" aria-hidden="true" />
              ) : revision.status === "failed" ? null : (
                <Spinner label="Parsing" />
              )}
              <span className="min-w-0 flex-1 truncate font-medium">{stage.file.name}</span>
              <RevisionStatusBadge status={revision.status} />
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs text-muted sm:grid-cols-4">
              <div>
                <dt className="inline">Size: </dt>
                <dd className="inline font-mono">{formatBytes(revision.source_file?.size_bytes ?? stage.file.size)}</dd>
              </div>
              <div>
                <dt className="inline">Revision: </dt>
                <dd className="inline font-mono">{revision.revision_number}</dd>
              </div>
              <div className="col-span-2 truncate" title={revision.source_sha256}>
                <dt className="inline">SHA-256: </dt>
                <dd className="inline font-mono">{revision.source_sha256.slice(0, 16)}…</dd>
              </div>
            </dl>
            {revision.status === "failed" ? (
              <ErrorState title="Parsing failed" description={`${revision.error_message ?? "Unknown error"} (${revision.error_code})`} />
            ) : null}
            {revision.status === "ready" ? (
              <p className="text-xs text-muted">
                {revision.object_counts.component_count ?? 0} components, {revision.object_counts.net_count ?? 0} nets,{" "}
                {revision.object_counts.layer_count ?? 0} layers
                {revision.warnings.length ? ` · ${revision.warnings.length} warning(s)` : ""}.{" "}
                <Link href={`/projects/${projectId}/designs/${stage.result.design.id}`} className="text-accent hover:underline">
                  Open design
                </Link>
              </p>
            ) : null}
          </div>
        ) : null}

        {stage.kind === "error" ? (
          <ErrorState
            title={stage.file ? `Couldn't upload ${stage.file.name}` : "Upload failed"}
            description={
              <>
                {stage.message}
                {stage.duplicateOf ? (
                  <>
                    {" "}
                    <Link href={`/projects/${projectId}/designs/${stage.duplicateOf.designId}`} className="text-accent hover:underline">
                      Open {stage.duplicateOf.name}
                    </Link>
                  </>
                ) : null}
              </>
            }
            action={
              <Button size="sm" variant="ghost" onClick={() => setStage({ kind: "idle" })}>
                Dismiss
              </Button>
            }
          />
        ) : null}
        {limits.error ? <ErrorState title="Couldn't load upload settings" description={errorMessage(limits.error)} /> : null}
      </CardContent>
    </Card>
  );
}
