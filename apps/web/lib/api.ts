import { createViaClient } from "@via/api-client";

/** Browser-side API client. Requests go to the same-origin `/api/*` rewrite. */
export const api = createViaClient();
