/** Standard API response envelope — canonical shared type. */
export type APIResponse<T> = {
  data: T | null;
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  } | null;
  meta: Record<string, unknown>;
};
