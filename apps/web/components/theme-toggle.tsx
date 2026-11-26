"use client";

import { Button } from "@via/ui";
import { Moon, Sun } from "lucide-react";

import type { Theme } from "@/lib/theme";
import { setTheme, useTheme } from "@/lib/use-theme";

export function ThemeToggle() {
  const theme = useTheme();
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <Button variant="ghost" size="icon" onClick={() => setTheme(next)} aria-label={`Switch to ${next} theme`} title={`Switch to ${next} theme`}>
      {theme === "dark" ? <Sun /> : <Moon />}
    </Button>
  );
}
