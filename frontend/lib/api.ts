import { clearToken, getToken } from "./auth";
import type {
  MediaUploadDetail,
  MediaUploadSummary,
  OverrideEntry,
  Student,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (res.status === 401) {
    clearToken();
    throw new ApiError(401, "Session expired. Please log in again.");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function login(username: string, password: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    throw new ApiError(res.status, "Invalid username or password");
  }
  const body = await res.json();
  return body.access_token as string;
}

export const api = {
  listStudents: () => request<Student[]>("/api/v1/students"),
  createStudent: (form: FormData) =>
    request<Student>("/api/v1/students", { method: "POST", body: form }),
  deleteStudent: (id: string) =>
    request<void>(`/api/v1/students/${id}`, { method: "DELETE" }),

  listMedia: () => request<MediaUploadSummary[]>("/api/v1/media"),
  getMedia: (id: string) => request<MediaUploadDetail>(`/api/v1/media/${id}`),
  uploadMedia: (form: FormData) =>
    request<{ media_id: string; status: string; message: string }>(
      "/api/v1/media/upload",
      { method: "POST", body: form }
    ),
  createDemo: () =>
    request<MediaUploadDetail>("/api/v1/media/demo", { method: "POST" }),
  commitReview: (id: string, overrides: OverrideEntry[], finalize: boolean) =>
    request<{ status: string; workflow_status: string; processed_url?: string }>(
      `/api/v1/media/${id}/review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ overrides, finalize }),
      }
    ),
};
