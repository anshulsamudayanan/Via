"use client";

import { Card, EmptyState, ErrorState, Skeleton, Table, TBody, TD, TH, THead, TR } from "@via/ui";
import { Download, FileStack } from "lucide-react";
import Link from "next/link";

import { useApi } from "@/components/api-context";
import { errorMessage } from "@/lib/errors";
import { formatBytes, formatDateTime, relativeTime } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

export function FilesTable({ projectId }: { projectId: string }) {
  const client = useApi();
  const files = useAsync(() => client.files.list(projectId), [client, projectId]);
  if (files.error) return <ErrorState title="Couldn't load files" description={errorMessage(files.error)} />;
  if (!files.data) return <Skeleton className="h-32 w-full" />;
  if (files.data.length === 0) {
    return (
      <Card>
        <EmptyState icon={<FileStack />} title="No files yet" description="Original uploads appear here, with their size and SHA-256 checksum." />
      </Card>
    );
  }
  return (
    <Card>
      <Table>
        <caption className="sr-only">Uploaded files</caption>
        <THead>
          <tr>
            <TH>File</TH>
            <TH className="hidden md:table-cell">Design</TH>
            <TH className="text-right">Size</TH>
            <TH className="hidden lg:table-cell">SHA-256</TH>
            <TH className="text-right">Uploaded</TH>
            <TH className="w-10"><span className="sr-only">Download</span></TH>
          </tr>
        </THead>
        <TBody>
          {files.data.map((f) => (
            <TR key={f.id}>
              <TD className="max-w-64 truncate font-mono text-xs">{f.original_filename}</TD>
              <TD className="hidden md:table-cell">
                <Link href={`/projects/${projectId}/designs/${f.design_id}`} className="hover:underline">
                  {f.design_name}
                </Link>{" "}
                <span className="text-xs text-muted">rev {f.revision_number}</span>
              </TD>
              <TD className="text-right font-mono text-xs tabular-nums">{formatBytes(f.size_bytes)}</TD>
              <TD className="hidden font-mono text-xs text-muted lg:table-cell" title={f.sha256}>{f.sha256.slice(0, 16)}…</TD>
              <TD className="text-right text-xs whitespace-nowrap text-muted" title={formatDateTime(f.created_at)}>{relativeTime(f.created_at)}</TD>
              <TD>
                <a
                  href={client.files.downloadUrl(f.id)}
                  className="inline-flex rounded-sm p-1 text-muted hover:bg-surface-hover hover:text-foreground"
                  aria-label={`Download ${f.original_filename}`}
                  download
                >
                  <Download className="size-4" />
                </a>
              </TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}
