import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { navigation, router } from "./helpers";

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  useSearchParams: () => navigation.search,
  usePathname: () => navigation.pathname,
  useParams: () => ({ projectId: "p1", designId: "d1" }),
}));

beforeEach(() => {
  navigation.search = new URLSearchParams();
  navigation.pathname = "/";
  for (const fn of Object.values(router)) fn.mockReset();
});

afterEach(cleanup);
