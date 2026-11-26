import { Activity, Boxes, CircuitBoard, FolderKanban, LayoutDashboard, type LucideIcon, ScanSearch, Settings } from "lucide-react";

export interface NavEntry {
  href?: string;
  label: string;
  icon: LucideIcon;
  /** Not built yet: shown disabled with a "Soon" badge and this explanation. */
  soon?: string;
}

export const NAV_GROUPS: { label: string; items: NavEntry[] }[] = [
  {
    label: "Workspace",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/projects", label: "Projects", icon: FolderKanban },
      { href: "/activity", label: "Activity", icon: Activity },
    ],
  },
  {
    label: "Engineering",
    items: [
      { href: "/designs", label: "Designs", icon: CircuitBoard },
      { label: "Analysis", icon: ScanSearch, soon: "A cross-project analysis view is coming soon. Each design has an Analysis tab." },
      { label: "Components", icon: Boxes, soon: "A cross-project component library is coming soon. Each design lists its components." },
    ],
  },
  { label: "Platform", items: [{ href: "/settings", label: "Settings", icon: Settings }] },
];

export const NAV_LINKS = NAV_GROUPS.flatMap((g) => g.items).filter((i): i is NavEntry & { href: string } => Boolean(i.href));

export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
