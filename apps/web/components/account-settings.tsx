"use client";

import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, ErrorState, Field, Input, Skeleton } from "@via/ui";
import { LogOut, Monitor } from "lucide-react";
import { type FormEvent, useState } from "react";

import { useApi } from "@/components/api-context";
import { MIN_PASSWORD_LENGTH, passwordError } from "@/components/auth/password-rules";
import { useSession } from "@/components/session";
import { errorMessage, fieldErrors } from "@/lib/errors";
import { formatDateTime, relativeTime } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

function Profile() {
  const client = useApi();
  const { me, setMe } = useSession();
  const [name, setName] = useState(me.user.display_name);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return setError("Enter your name.");
    setSaving(true);
    setError(null);
    try {
      const updated = await client.users.updateMe({ display_name: name.trim() });
      setMe(updated);
      setName(updated.user.display_name);
      setSaved(true);
    } catch (err) {
      setError(fieldErrors(err).display_name ?? errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Profile</CardTitle>
          <CardDescription>Your name is shown to people you share projects with.</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-3" noValidate>
          <Field label="Email" hint="Email changes aren't supported yet.">
            {(p) => <Input {...p} value={me.user.email} disabled readOnly />}
          </Field>
          <Field label="Name" error={error}>
            {(p) => (
              <Input
                {...p}
                maxLength={120}
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setSaved(false);
                }}
              />
            )}
          </Field>
          <div className="flex items-center justify-end gap-3">
            {saved ? (
              <span role="status" className="text-xs text-success">
                Saved
              </span>
            ) : null}
            <Button type="submit" variant="primary" disabled={saving || name === me.user.display_name}>
              Save
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function Password({ onChanged }: { onChanged: () => void }) {
  const client = useApi();
  const { me } = useSession();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [errors, setErrors] = useState<{ current?: string; next?: string; form?: string }>({});
  const [done, setDone] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setDone(null);
    const problem = passwordError(next, me.user.email);
    const found = { ...(current ? {} : { current: "Enter your current password." }), ...(problem ? { next: problem } : {}) };
    setErrors(found);
    if (Object.keys(found).length) return;
    setSaving(true);
    try {
      setDone((await client.users.changePassword(current, next)).message);
      setCurrent("");
      setNext("");
      onChanged();
    } catch (err) {
      setErrors({ form: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Password</CardTitle>
          <CardDescription>Changing your password signs out your other sessions.</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-3" noValidate>
          {errors.form ? <ErrorState title={errors.form} /> : null}
          {done ? (
            <p role="status" className="text-xs text-success">
              {done}
            </p>
          ) : null}
          <Field label="Current password" error={errors.current}>
            {(p) => <Input {...p} type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />}
          </Field>
          <Field label="New password" error={errors.next} hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}>
            {(p) => <Input {...p} type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />}
          </Field>
          <div className="flex justify-end">
            <Button type="submit" variant="primary" disabled={saving}>
              {saving ? "Changing..." : "Change password"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function describeAgent(ua: string | null): string {
  if (!ua) return "Unknown device";
  const browser = /Firefox\//.test(ua) ? "Firefox" : /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : null;
  const os = /Windows/.test(ua) ? "Windows" : /Mac OS X/.test(ua) ? "macOS" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Linux/.test(ua) ? "Linux" : null;
  return [browser, os].filter(Boolean).join(" on ") || ua.slice(0, 60);
}

function Sessions({ version }: { version: number }) {
  const client = useApi();
  const sessions = useAsync(() => client.auth.sessions(), [client, version]);
  const [error, setError] = useState<string | null>(null);

  async function revoke(id: string) {
    setError(null);
    try {
      await client.auth.revokeSession(id);
      sessions.reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Active sessions</CardTitle>
          <CardDescription>Devices currently signed in to your account.</CardDescription>
        </div>
      </CardHeader>
      {error ? <ErrorState className="m-3" title={error} /> : null}
      {sessions.loading && !sessions.data ? (
        <CardContent>
          <Skeleton className="h-12 w-full" />
        </CardContent>
      ) : sessions.error ? (
        <ErrorState className="m-3" title="Couldn't load sessions" description={errorMessage(sessions.error)} />
      ) : (
        <ul className="divide-y divide-border">
          {(sessions.data ?? []).map((s) => (
            <li key={s.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
              <Monitor className="size-4 shrink-0 text-subtle" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate">{describeAgent(s.user_agent)}</span>
                  {s.current ? <Badge tone="success">This device</Badge> : null}
                </div>
                <div className="text-xs text-muted">
                  {s.ip_address ?? "Unknown IP"} · active {relativeTime(s.last_seen_at)} · signed in {formatDateTime(s.created_at)}
                </div>
              </div>
              {!s.current ? (
                <Button size="sm" variant="ghost" onClick={() => void revoke(s.id)}>
                  Sign out
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function AccountSettings() {
  const { signOut } = useSession();
  const [version, setVersion] = useState(0);
  return (
    <div className="max-w-3xl space-y-4">
      <Profile />
      <Password onChanged={() => setVersion((v) => v + 1)} />
      <Sessions version={version} />
      <div className="flex justify-end">
        <Button variant="secondary" onClick={() => void signOut()}>
          <LogOut /> Sign out
        </Button>
      </div>
    </div>
  );
}
