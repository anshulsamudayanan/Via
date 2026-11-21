import type {
  ActivityItem,
  ErrorResponse,
  LivenessResponse,
  MeResponse,
  Message,
  Organization,
  Page,
  Project,
  ProjectMember,
  ProjectRole,
  ProjectSort,
  ProjectStatusFilter,
  ProjectSummary,
  ProjectVisibility,
  ReadinessResponse,
  SessionInfo,
} from "@via/types";

/**
 * Typed client for the VIA API.
 *
 * The browser talks to the API through the web app's same-origin `/api/*`
 * rewrite, so the default `baseUrl` is "". Cookies are sent automatically
 * (same-origin). No credentials or storage secrets ever live in the client.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, requestId: string | null = null, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }

  /** True when the API could not be reached at all (network error, proxy down). */
  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

export interface ClientOptions {
  baseUrl?: string;
  fetch?: typeof fetch;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  /** HTTP statuses (besides 2xx) whose body is a valid typed response, e.g. readiness 503. */
  acceptStatuses?: number[];
}

const UNSAFE_METHODS = new Set(["POST", "PATCH", "PUT", "DELETE"]);

function isErrorResponse(value: unknown): value is ErrorResponse {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const err = (value as { error: unknown }).error;
  return typeof err === "object" && err !== null && "code" in err && "message" in err;
}

export function createViaClient(options: ClientOptions = {}) {
  const baseUrl = (options.baseUrl ?? "").replace(/\/$/, "");
  const doFetch = options.fetch ?? globalThis.fetch.bind(globalThis);

  async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
    const method = opts.method ?? "GET";
    const headers: Record<string, string> = { Accept: "application/json" };
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    // CSRF defence: the API requires this header on cookie-authenticated unsafe requests.
    if (UNSAFE_METHODS.has(method)) headers["X-VIA-Request"] = "1";

    let response: Response;
    try {
      response = await doFetch(`${baseUrl}${path}`, {
        method,
        headers,
        body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
        credentials: "same-origin",
        signal: opts.signal,
      });
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new ApiError(0, "network_error", "Could not reach the VIA API. Check your connection and try again.");
    }

    const text = await response.text();
    let data: unknown = undefined;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = undefined;
      }
    }

    if (response.ok || opts.acceptStatuses?.includes(response.status)) {
      if (data === undefined && text) {
        throw new ApiError(response.status, "invalid_response", "The API returned an unexpected response.");
      }
      return data as T;
    }
    if (isErrorResponse(data)) {
      const { code, message, request_id, details } = data.error;
      throw new ApiError(response.status, code, message, request_id, details);
    }
    throw new ApiError(
      response.status,
      "http_error",
      `The API returned HTTP ${response.status}.`,
      response.headers.get("x-request-id"),
    );
  }

  const q = (params: Record<string, string | number | undefined | null>) => {
    const search = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") search.set(k, String(v));
    const s = search.toString();
    return s ? `?${s}` : "";
  };
  const enc = encodeURIComponent;

  return {
    request,
    health: {
      live: (signal?: AbortSignal) => request<LivenessResponse>("/api/v1/health", { signal }),
      ready: (signal?: AbortSignal) =>
        request<ReadinessResponse>("/api/v1/health/ready", { signal, acceptStatuses: [503] }),
    },
    auth: {
      register: (body: { email: string; password: string; display_name: string }) =>
        request<MeResponse>("/api/v1/auth/register", { method: "POST", body }),
      login: (body: { email: string; password: string }) =>
        request<MeResponse>("/api/v1/auth/login", { method: "POST", body }),
      logout: () => request<Message>("/api/v1/auth/logout", { method: "POST" }),
      me: (signal?: AbortSignal) => request<MeResponse>("/api/v1/auth/me", { signal }),
      sessions: () => request<SessionInfo[]>("/api/v1/auth/sessions"),
      revokeSession: (id: string) => request<void>(`/api/v1/auth/sessions/${enc(id)}`, { method: "DELETE" }),
      requestPasswordReset: (email: string) =>
        request<Message>("/api/v1/auth/password-reset/request", { method: "POST", body: { email } }),
      confirmPasswordReset: (token: string, new_password: string) =>
        request<Message>("/api/v1/auth/password-reset/confirm", { method: "POST", body: { token, new_password } }),
    },
    users: {
      updateMe: (body: { display_name: string }) => request<MeResponse>("/api/v1/users/me", { method: "PATCH", body }),
      changePassword: (current_password: string, new_password: string) =>
        request<Message>("/api/v1/users/me/password", { method: "POST", body: { current_password, new_password } }),
    },
    organizations: {
      list: () => request<Organization[]>("/api/v1/organizations"),
      create: (name: string) => request<Organization>("/api/v1/organizations", { method: "POST", body: { name } }),
    },
    projects: {
      list: (
        params: {
          q?: string;
          status?: ProjectStatusFilter;
          organization_id?: string;
          sort?: ProjectSort;
          limit?: number;
          offset?: number;
        } = {},
        signal?: AbortSignal,
      ) => request<Page<Project>>(`/api/v1/projects${q(params)}`, { signal }),
      summary: () => request<ProjectSummary>("/api/v1/projects/summary"),
      get: (id: string, signal?: AbortSignal) => request<Project>(`/api/v1/projects/${enc(id)}`, { signal }),
      create: (body: { name: string; description?: string; organization_id?: string; visibility?: ProjectVisibility }) =>
        request<Project>("/api/v1/projects", { method: "POST", body }),
      update: (id: string, body: { name?: string; description?: string; visibility?: ProjectVisibility }) =>
        request<Project>(`/api/v1/projects/${enc(id)}`, { method: "PATCH", body }),
      archive: (id: string) => request<Project>(`/api/v1/projects/${enc(id)}/archive`, { method: "POST" }),
      unarchive: (id: string) => request<Project>(`/api/v1/projects/${enc(id)}/unarchive`, { method: "POST" }),
      delete: (id: string) => request<void>(`/api/v1/projects/${enc(id)}`, { method: "DELETE" }),
      members: (id: string) => request<ProjectMember[]>(`/api/v1/projects/${enc(id)}/members`),
      addMember: (id: string, email: string, role: Exclude<ProjectRole, "owner">) =>
        request<ProjectMember>(`/api/v1/projects/${enc(id)}/members`, { method: "POST", body: { email, role } }),
      updateMember: (id: string, userId: string, role: Exclude<ProjectRole, "owner">) =>
        request<ProjectMember>(`/api/v1/projects/${enc(id)}/members/${enc(userId)}`, { method: "PATCH", body: { role } }),
      removeMember: (id: string, userId: string) =>
        request<void>(`/api/v1/projects/${enc(id)}/members/${enc(userId)}`, { method: "DELETE" }),
    },
    activity: {
      list: (params: { project_id?: string; limit?: number; offset?: number } = {}) =>
        request<Page<ActivityItem>>(`/api/v1/activity${q(params)}`),
    },
  };
}

export type ViaClient = ReturnType<typeof createViaClient>;
