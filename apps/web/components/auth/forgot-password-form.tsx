"use client";

import { Button, ErrorState, Field, Input } from "@via/ui";
import { AlertCircle, MailCheck } from "lucide-react";
import Link from "next/link";
import { type FormEvent, useState } from "react";

import { useApi } from "@/components/api-context";
import { AuthCard } from "@/components/auth/auth-card";
import { emailError } from "@/components/auth/password-rules";
import { errorMessage } from "@/lib/errors";

export function ForgotPasswordForm() {
  const client = useApi();
  const [email, setEmail] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const invalid = emailError(email);
    setFieldError(invalid);
    setFormError(null);
    if (invalid) return;
    setSubmitting(true);
    try {
      setSent((await client.auth.requestPasswordReset(email.trim())).message);
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Reset your password"
      subtitle="We'll email you a link to choose a new password."
      footer={
        <Link href="/login" className="text-accent hover:underline">
          Back to sign in
        </Link>
      }
    >
      {sent ? (
        <div role="status" className="flex items-start gap-3 text-sm">
          <MailCheck className="mt-0.5 size-4 text-success" aria-hidden="true" />
          <p>{sent}</p>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="space-y-3" noValidate>
          {formError ? <ErrorState icon={<AlertCircle />} title={formError} /> : null}
          <Field label="Email" error={fieldError}>
            {(p) => <Input {...p} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />}
          </Field>
          <Button type="submit" variant="primary" className="w-full" disabled={submitting}>
            {submitting ? "Sending..." : "Send reset link"}
          </Button>
        </form>
      )}
    </AuthCard>
  );
}
