"use client";

import type { FeedbackType, KnowledgeUsed, Recommendation } from "@via/types";
import { Badge, Button, Textarea } from "@via/ui";
import Link from "next/link";
import { useState } from "react";

import { useApi } from "@/components/api-context";
import { errorMessage } from "@/lib/errors";
import { FEEDBACK_LABEL, LEARN_VERIFICATION_LABEL, NEEDS_EXPLANATION } from "@/lib/learn";

const QUICK: FeedbackType[] = ["helpful", "unhelpful"];
const WRITTEN: FeedbackType[] = ["correction", "incorrect_assumption", "comment"];

/** Library notes the model was shown for this recommendation. Only a cited note influenced the answer. */
function Knowledge({ items }: { items: KnowledgeUsed[] }) {
  if (!items.length) return null;
  return (
    <div className="text-xs text-muted">
      <p>VIA Learn notes shown to the model (only cited ones influenced this answer):</p>
      <ul className="mt-0.5 space-y-0.5">
        {items.map((k) => (
          <li key={k.entry_id} className="flex flex-wrap items-center gap-1.5">
            <Link href={`/learn?entry=${k.entry_id}`} className="text-foreground hover:underline">
              {k.title || "Withdrawn entry"}
            </Link>
            <Badge>{LEARN_VERIFICATION_LABEL[k.verification_status]}</Badge>
            <span>{k.cited ? "cited" : "shown, not cited"}</span>
            {k.source ? <span>· {k.source}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Feedback and "contribute" controls for one recommendation. Accepting is recorded elsewhere and is not proof of correctness. */
export function RecommendationFeedback({ rec, canEdit, isOwner }: { rec: Recommendation; canEdit: boolean; isOwner: boolean }) {
  const client = useApi();
  const [open, setOpen] = useState<FeedbackType | null>(null);
  const [text, setText] = useState("");
  const [sent, setSent] = useState<string[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function send(type: FeedbackType, explanation?: string) {
    setBusy(true);
    setError(null);
    try {
      await client.learn.feedback(rec.id, { feedback_type: type, explanation: explanation || undefined });
      setSent((s) => [...s, FEEDBACK_LABEL[type]]);
      setOpen(null);
      setText("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function contribute() {
    setBusy(true);
    setError(null);
    try {
      await client.learn.contributeRecommendation(rec.id);
      setNote("Draft created with part references, net names and design names removed. Review it under VIA Learn → My contributions before submitting.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-1.5 pt-1">
      <Knowledge items={rec.knowledge ?? []} />
      {canEdit ? (
        <div className="flex flex-wrap items-center gap-1.5">
          {QUICK.map((t) => (
            <Button key={t} size="sm" variant="ghost" disabled={busy} onClick={() => void send(t)}>
              {FEEDBACK_LABEL[t]}
            </Button>
          ))}
          {WRITTEN.map((t) => (
            <Button key={t} size="sm" variant="ghost" aria-pressed={open === t} onClick={() => setOpen(open === t ? null : t)}>
              {FEEDBACK_LABEL[t]}
            </Button>
          ))}
          {isOwner ? (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => void contribute()}>
              Contribute to VIA Learn
            </Button>
          ) : null}
        </div>
      ) : null}
      {open ? (
        <div className="space-y-1.5">
          <Textarea
            aria-label={`${FEEDBACK_LABEL[open]} details`}
            value={text}
            maxLength={4000}
            onChange={(e) => setText(e.target.value)}
            placeholder={NEEDS_EXPLANATION.has(open) ? "Say what is wrong or what you would change" : "Optional"}
          />
          <Button size="sm" disabled={busy || (NEEDS_EXPLANATION.has(open) && !text.trim())} onClick={() => void send(open, text.trim())}>
            Send {FEEDBACK_LABEL[open].toLowerCase()}
          </Button>
        </div>
      ) : null}
      {sent.length ? <p role="status" className="text-xs text-muted">Feedback recorded: {sent.join(", ")}.</p> : null}
      {note ? <p role="status" className="text-xs text-muted">{note}</p> : null}
      {error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}
    </div>
  );
}
