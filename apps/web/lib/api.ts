/** API base URL — reads from env or defaults to localhost:8000. */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

/** Build a full API URL from a path. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
