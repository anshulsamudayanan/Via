import path from "node:path";

import { defineConfig } from "vitest/config";

export default defineConfig({
  // shadcn components import their helpers by package name (`@via/ui/cn`); resolve those to src.
  resolve: { alias: [{ find: /^@via\/ui\/(.*)$/, replacement: `${path.resolve(import.meta.dirname, "src")}/$1` }] },
  test: { environment: "jsdom" },
});
