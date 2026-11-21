"use client";

import { AccountSettings } from "@/components/account-settings";
import { PageHeader } from "@/components/app-shell";

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Account settings" description="Your profile, password and signed-in devices." />
      <AccountSettings />
    </>
  );
}
