/** Standard API response envelope — mirrors backend APIResponse. */
export type APIResponse<T> = {
  data: T | null;
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  } | null;
  meta: Record<string, unknown>;
};
