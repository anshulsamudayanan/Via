"use client";

/*
 * Adapted from the 21st.dev "File Dropzone" (@amankaushik481): accept/reject drag states, a crisp
 * SVG dashed border that marches while dragging, a file row with progress, retry and remove, and a
 * screen-reader announcement. Rewired to VIA: one board at a time into a project you can edit, the
 * real upload endpoint (with byte progress and cancel), the API's own limits and error messages.
 */

import { ApiError } from "@via/api-client";
import type { ImportResponse, UploadLimits } from "@via/types";
import { cn, Skeleton, useToast } from "@via/ui";
import { ArrowUp, Check, RotateCw, X } from "lucide-react";
import Link from "next/link";
import { type DragEvent, forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

import { useApi } from "@/components/api-context";
import { validateFile } from "@/components/designs/upload-panel";
import { errorMessage } from "@/lib/errors";
import { formatBytes } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

type Stage =
  | { kind: "idle" }
  | { kind: "uploading"; file: File; loaded: number; total: number }
  | { kind: "done"; file: File; result: ImportResponse; projectId: string }
  | { kind: "error"; file: File; message: string; retry: boolean; duplicateOf?: { href: string; name: string } };

export interface BoardDropzoneHandle {
  /** Open the file picker (the page header's Upload button). */
  browse: () => void;
}

function extOf(name: string) {
  const lower = name.toLowerCase();
  if (lower.endsWith(".kicad_pcb")) return "PCB";
  const e = name.split(".").pop();
  return e && e !== name ? e.slice(0, 4).toUpperCase() : "FILE";
}

export const BoardDropzone = forwardRef<BoardDropzoneHandle>(function BoardDropzone(_props, ref) {
  const client = useApi();
  const { push } = useToast();
  const limits = useAsync(() => client.pcb.limits(), [client]);
  const projects = useAsync((s) => client.projects.list({ status: "active", sort: "updated", limit: 100 }, s), [client]);
  const writable = (projects.data?.items ?? []).filter((p) => p.my_role !== "viewer");
  const [choice, setChoice] = useState("");
  const projectId = writable.some((p) => p.id === choice) ? choice : (writable[0]?.id ?? "");

  const [stage, setStage] = useState<Stage>({ kind: "idle" });
  const [drag, setDrag] = useState<"idle" | "accept" | "reject">("idle");
  const [announce, setAnnounce] = useState("");
  const depth = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => () => abortRef.current?.abort(), []);

  const disabled = !projectId || stage.kind === "uploading";
  useImperativeHandle(ref, () => ({ browse: () => !disabled && inputRef.current?.click() }), [disabled]);

  async function start(file: File) {
    if (!projectId) return;
    let lim: UploadLimits | undefined = limits.data;
    try {
      lim ??= await client.pcb.limits();
    } catch (err) {
      setStage({ kind: "error", file, message: errorMessage(err), retry: true });
      return;
    }
    const problem = validateFile(file, lim);
    if (problem) {
      setStage({ kind: "error", file, message: problem, retry: false });
      setAnnounce(`${file.name} can't be uploaded: ${problem}`);
      return;
    }
    const ac = new AbortController();
    abortRef.current = ac;
    const target = projectId;
    setStage({ kind: "uploading", file, loaded: 0, total: file.size });
    setAnnounce(`Uploading ${file.name}`);
    try {
      const result = await client.pcb.upload({
        projectId: target,
        file,
        signal: ac.signal,
        onProgress: (loaded, total) => setStage({ kind: "uploading", file, loaded, total }),
      });
      setStage({ kind: "done", file, result, projectId: target });
      setAnnounce(`${file.name} uploaded`);
      push({
        tone: "success",
        title: "Board uploaded",
        description: `${result.design.name}, revision ${result.revision.revision_number}. VIA is parsing it now.`,
        action: (
          <Link href={`/projects/${target}/designs/${result.design.id}`} className="font-medium text-accent hover:underline">
            Open design
          </Link>
        ),
      });
      void projects.reload();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setStage({ kind: "idle" });
        setAnnounce("Upload cancelled");
        return;
      }
      const dup =
        err instanceof ApiError && err.code === "duplicate_file" && err.details && typeof err.details === "object"
          ? (err.details as { design_id?: string; design_name?: string })
          : null;
      const message = errorMessage(err);
      setStage({
        kind: "error",
        file,
        message,
        retry: !dup,
        duplicateOf: dup?.design_id ? { href: `/projects/${target}/designs/${dup.design_id}`, name: dup.design_name ?? "the existing design" } : undefined,
      });
      push({ tone: "error", title: "Upload failed", description: message });
    } finally {
      abortRef.current = null;
    }
  }

  function dragKind(e: DragEvent): "accept" | "reject" {
    const files = Array.from(e.dataTransfer.items ?? []).filter((i) => i.kind === "file");
    // Browsers don't expose names while dragging and .kicad_pcb has no MIME type: only the count is known.
    return files.length > 1 ? "reject" : "accept";
  }

  const accept = limits.data?.formats.flatMap((f) => f.extensions).join(",") ?? ".kicad_pcb,.zip";
  const hint = limits.data
    ? `${limits.data.formats.flatMap((f) => f.extensions).join(" or ")} · up to ${formatBytes(limits.data.max_upload_bytes)}`
    : "Loading upload limits…";
  const over = drag !== "idle";
  const reject = drag === "reject";

  if (!projects.data) return <Skeleton className="h-[172px] w-full" />;

  if (writable.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border-strong px-4 py-6 text-center text-xs text-muted">
        You can&apos;t upload to any active project. Create one, or ask a project owner for editor access.
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      <label className="flex items-center gap-2 text-xs text-muted">
        <span className="shrink-0">Upload to</span>
        <select
          value={projectId}
          onChange={(e) => setChoice(e.target.value)}
          disabled={stage.kind === "uploading"}
          className="h-7 min-w-0 flex-1 cursor-pointer truncate rounded-md border border-border bg-surface-sunken px-1.5 text-xs text-foreground outline-none focus:border-border-strong disabled:opacity-60"
        >
          {writable.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>

      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        tabIndex={-1}
        accept={accept}
        aria-label="Choose a board file"
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) void start(file);
        }}
      />
      <div
        id="board-dropzone"
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled || undefined}
        aria-describedby="board-dropzone-hint"
        aria-label="Upload a KiCad board: drop a file or press Enter to browse"
        data-drag={drag}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !disabled) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragEnter={(e) => {
          e.preventDefault();
          if (disabled) return;
          depth.current += 1;
          setDrag(dragKind(e));
        }}
        onDragOver={(e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = reject || disabled ? "none" : "copy";
        }}
        onDragLeave={() => {
          depth.current = Math.max(0, depth.current - 1);
          if (depth.current === 0) setDrag("idle");
        }}
        onDrop={(e) => {
          e.preventDefault();
          depth.current = 0;
          setDrag("idle");
          const files = e.dataTransfer.files;
          if (disabled || !files?.length) return;
          if (files.length > 1) {
            setAnnounce("Drop one board at a time");
            return;
          }
          void start(files[0]!);
        }}
        className={cn(
          "group/drop relative isolate flex w-full cursor-pointer flex-col items-center justify-center gap-2.5 overflow-hidden rounded-lg px-4 py-6 text-center outline-none transition-colors duration-150",
          !over && "hover:bg-surface-hover",
          over && !reject && "bg-accent-soft",
          reject && "bg-danger-soft",
          disabled && "cursor-default opacity-60",
        )}
      >
        {/* Hairline dashed border: stays crisp at any size and marches while a file is over it. */}
        <svg aria-hidden="true" className="pointer-events-none absolute inset-[0.5px] size-[calc(100%-1px)] overflow-visible">
          <rect
            width="100%"
            height="100%"
            rx="5.5"
            fill="none"
            strokeWidth="1"
            strokeDasharray="6 5"
            className={cn(
              "transition-[stroke] duration-150",
              reject ? "stroke-danger" : over ? "stroke-accent" : "stroke-border-strong group-hover/drop:stroke-subtle",
              over && !reject && "via-dash-march",
            )}
          />
        </svg>
        <span
          className={cn(
            "grid size-9 place-items-center rounded-md border transition-[transform,background-color,border-color,color] duration-200 motion-reduce:transition-none [&>svg]:size-4",
            reject
              ? "border-danger/40 bg-surface text-danger"
              : over
                ? "-translate-y-0.5 border-accent bg-accent text-accent-foreground"
                : "border-border bg-surface-raised text-muted group-hover/drop:text-foreground",
          )}
        >
          {reject ? <X aria-hidden="true" /> : <ArrowUp aria-hidden="true" />}
        </span>
        <div className="space-y-0.5">
          <p className="text-[13px] font-medium text-foreground">{reject ? "One board at a time" : over ? "Release to upload" : "Drop a KiCad board"}</p>
          <p className="text-xs text-muted">
            <span className="font-medium text-foreground underline decoration-border-strong underline-offset-[3px]">Browse</span> or drag a file here
          </p>
          <p id="board-dropzone-hint" className="pt-1 font-mono text-[11px] text-subtle">
            {hint}
          </p>
        </div>
      </div>

      {stage.kind !== "idle" ? (
        <FileRow
          stage={stage}
          onCancel={() => abortRef.current?.abort()}
          onRetry={stage.kind === "error" && stage.retry ? () => void start(stage.file) : undefined}
          onRemove={() => setStage({ kind: "idle" })}
        />
      ) : null}
      <span className="sr-only" aria-live="polite">
        {announce}
      </span>
    </div>
  );
});

function FileRow({ stage, onCancel, onRetry, onRemove }: { stage: Exclude<Stage, { kind: "idle" }>; onCancel: () => void; onRetry?: () => void; onRemove: () => void }) {
  const error = stage.kind === "error";
  const pct = stage.kind === "uploading" ? Math.round((stage.loaded / Math.max(stage.total, 1)) * 100) : 100;
  return (
    <div
      className={cn(
        "relative flex animate-fade-in items-center gap-3 overflow-hidden rounded-lg border bg-surface p-2.5 pr-2 motion-reduce:animate-none",
        error ? "border-danger/40" : "border-border",
      )}
    >
      <span className="grid size-9 shrink-0 place-items-center rounded-md border border-border bg-surface-sunken font-mono text-[9px] font-semibold tracking-[0.04em] text-muted">
        {extOf(stage.file.name)}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-[13px] font-medium text-foreground">{stage.file.name}</p>
          {stage.kind === "done" ? (
            <span className="grid size-4 shrink-0 place-items-center rounded-full bg-success text-background">
              <Check className="size-2.5" strokeWidth={3} aria-hidden="true" />
            </span>
          ) : null}
        </div>
        <p className={cn("mt-0.5 text-xs tabular-nums", error ? "text-danger" : "text-muted")}>
          {stage.kind === "error" ? (
            <>
              {stage.message}
              {stage.duplicateOf ? (
                <>
                  {" "}
                  <Link href={stage.duplicateOf.href} className="font-medium underline">
                    Open {stage.duplicateOf.name}
                  </Link>
                </>
              ) : null}
            </>
          ) : stage.kind === "uploading" ? (
            `${formatBytes(stage.loaded)} of ${formatBytes(stage.total)} · ${pct}%`
          ) : (
            <>
              {formatBytes(stage.file.size)} · uploaded, parsing.{" "}
              <Link href={`/projects/${stage.projectId}/designs/${stage.result.design.id}`} className="font-medium text-accent hover:underline">
                Open design
              </Link>
            </>
          )}
        </p>
      </div>
      {onRetry ? (
        <button type="button" onClick={onRetry} aria-label={`Retry ${stage.file.name}`} className="grid size-7 place-items-center rounded-md text-muted hover:bg-surface-hover hover:text-foreground">
          <RotateCw className="size-3.5" aria-hidden="true" />
        </button>
      ) : null}
      <button
        type="button"
        onClick={stage.kind === "uploading" ? onCancel : onRemove}
        aria-label={stage.kind === "uploading" ? "Cancel upload" : `Dismiss ${stage.file.name}`}
        className="grid size-7 place-items-center rounded-md text-subtle hover:bg-surface-hover hover:text-foreground"
      >
        <X className="size-3.5" aria-hidden="true" />
      </button>
      {stage.kind === "uploading" ? (
        <span
          role="progressbar"
          aria-label="Upload progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          className="absolute inset-x-0 bottom-0 h-0.5 bg-surface-hover"
        >
          <span className="block h-full origin-left bg-accent transition-transform duration-200" style={{ transform: `scaleX(${pct / 100})` }} />
        </span>
      ) : null}
    </div>
  );
}
