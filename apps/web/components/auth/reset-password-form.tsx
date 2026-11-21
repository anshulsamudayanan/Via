"use client";

import { Button, ErrorState, Field, Input } from "@via/ui";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";

import { useApi } from "@/components/api-context";
import { AuthCard } from "@/components/auth/auth-card";
import { MIN_PASSWORD_LENGTH, passwordError } from "@/components/auth/password-rules";
import { errorMessage } from "@/lib/errors";

export function ResetPasswordForm() {
  const client = useApi();
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<{ password?: string; confirm?: string; form?: string }>({});
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const next: typeof errors = {};
    const p = passwordError(password);
    if (p) next.password = p;
    if (confirm !== password) next.confirm = "Passwords don't match.";
    setErrors(next);
    if (Object.keys(next).length) return;
    setSubmitting(true);
    try {
      await client.auth.confirmPasswordReset(token, password);
      setDone(true);
    } catch (err) {
      setErrors({ form: errorMessage(err) });
    } finally {
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <AuthCard title="Reset link missing">
        <p className="text-sm text-muted">
          This page needs the link from your reset email.{" "}
          <Link href="/forgot-password" className="text-accent hover:underline">
            Request a new link
          </Link>
          .
        </p>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Choose a new password" subtitle="This signs you out on all devices.">
      {done ? (
        <div role="status" className="space-y-3 text-sm">
          <p className="flex items-center gap-2">
            <CheckCircle2 className="size-4 text-success" aria-hidden="true" /> Your password has been changed.
          </p>
          <Button asChild variant="primary" className="w-full">
            <Link href="/login">Sign in</Link>
          </Button>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="space-y-3" noValidate>
          {errors.form ? (
            <ErrorState
              icon={<AlertCircle />}
              title={errors.form}
              description={
                <Link href="/forgot-password" className="text-accent hover:underline">
                  Request a new link
                </Link>
              }
            />
          ) : null}
          <Field label="New password" error={errors.password} hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}>
            {(p) => <Input {...p} type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />}
          </Field>
          <Field label="Confirm new password" error={errors.confirm}>
            {(p) => <Input {...p} type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />}
          </Field>
          <Button type="submit" variant="primary" className="w-full" disabled={submitting}>
            {submitting ? "Saving..." : "Set new password"}
          </Button>
        </form>
      )}
    </AuthCard>
  );
}
