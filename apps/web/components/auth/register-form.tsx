"use client";

import { ApiError } from "@via/api-client";
import { Button, ErrorState, Field, Input } from "@via/ui";
import { AlertCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { useApi } from "@/components/api-context";
import { AuthCard } from "@/components/auth/auth-card";
import { emailError, MIN_PASSWORD_LENGTH, passwordError } from "@/components/auth/password-rules";
import { errorMessage, fieldErrors } from "@/lib/errors";

type Errors = Partial<Record<"display_name" | "email" | "password" | "form", string>>;

export function RegisterForm() {
  const client = useApi();
  const router = useRouter();
  const [form, setForm] = useState({ display_name: "", email: "", password: "" });
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }));

  function validate(): Errors {
    const next: Errors = {};
    if (!form.display_name.trim()) next.display_name = "Enter your name.";
    const e = emailError(form.email);
    if (e) next.email = e;
    const p = passwordError(form.password, form.email);
    if (p) next.password = p;
    return next;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length) return;
    setSubmitting(true);
    try {
      await client.auth.register({ display_name: form.display_name.trim(), email: form.email.trim(), password: form.password });
      router.replace("/dashboard");
      router.refresh();
    } catch (err) {
      const fields = fieldErrors(err);
      if (err instanceof ApiError && err.code === "email_taken") setErrors({ email: err.message });
      else if (err instanceof ApiError && err.code === "weak_password") setErrors({ password: err.message });
      else if (Object.keys(fields).length) setErrors(fields);
      else setErrors({ form: errorMessage(err) });
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Create your VIA account"
      subtitle="Your projects are private unless you choose to share them."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="text-accent hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-3" noValidate>
        {errors.form ? <ErrorState icon={<AlertCircle />} title={errors.form} /> : null}
        <Field label="Name" error={errors.display_name}>
          {(p) => <Input {...p} autoComplete="name" maxLength={120} value={form.display_name} onChange={set("display_name")} />}
        </Field>
        <Field label="Email" error={errors.email}>
          {(p) => <Input {...p} type="email" autoComplete="email" value={form.email} onChange={set("email")} />}
        </Field>
        <Field label="Password" error={errors.password} hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}>
          {(p) => <Input {...p} type="password" autoComplete="new-password" value={form.password} onChange={set("password")} />}
        </Field>
        <Button type="submit" variant="primary" className="w-full" disabled={submitting}>
          {submitting ? "Creating account..." : "Create account"}
        </Button>
      </form>
    </AuthCard>
  );
}
