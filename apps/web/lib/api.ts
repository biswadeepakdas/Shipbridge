/** API base URL — reads from env or defaults to Railway production. */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://shipbridge-production.up.railway.app";

/** Build a full API URL from a path. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
