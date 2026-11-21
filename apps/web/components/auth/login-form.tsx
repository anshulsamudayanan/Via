"use client";

import { Button, ErrorState, Field, Input } from "@via/ui";
import { AlertCircle } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";

import { useApi } from "@/components/api-context";
import { AuthCard } from "@/components/auth/auth-card";
import { errorMessage, safeNext } from "@/lib/errors";

export function LoginForm() {
  const client = useApi();
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await client.auth.login({ email: email.trim(), password });
      router.replace(safeNext(params.get("next")));
      router.refresh();
    } catch (err) {
      setError(errorMessage(err));
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Sign in to VIA"
      footer={
        <>
          New to VIA?{" "}
          <Link href="/register" className="text-accent hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-3" noValidate>
        {error ? <ErrorState icon={<AlertCircle />} title={error} /> : null}
        <Field label="Email">
          {(p) => (
            <Input {...p} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          )}
        </Field>
        <Field label="Password">
          {(p) => (
            <Input
              {...p}
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </Field>
        <div className="flex items-center justify-between pt-1">
          <Link href="/forgot-password" className="text-xs text-muted hover:text-foreground hover:underline">
            Forgot password?
          </Link>
          <Button type="submit" variant="primary" disabled={submitting || !email || !password}>
            {submitting ? "Signing in..." : "Sign in"}
          </Button>
        </div>
      </form>
    </AuthCard>
  );
}
