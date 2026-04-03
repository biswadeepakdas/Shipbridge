/** useApi hook — API client with retry logic, abort controller, loading/error states. */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { APIResponse } from "@/types/api";

interface UseApiState<T> {
  data: T | null;
  error: string | null;
  isLoading: boolean;
}

interface UseApiOptions {
  retries?: number;
  retryDelayMs?: number;
}

const DEFAULT_OPTIONS: UseApiOptions = {
  retries: 3,
  retryDelayMs: 1000,
};

async function fetchWithRetry(
  url: string,
  options: RequestInit,
  retries: number,
  retryDelay: number,
): Promise<Response> {
  let lastError: Error | null = null;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetch(url, options);
      if (response.ok || response.status < 500) {
        return response;
      }
      lastError = new Error(`HTTP ${response.status}`);
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
    }
    if (attempt < retries) {
      await new Promise((r) => setTimeout(r, retryDelay * (attempt + 1)));
    }
  }
  throw lastError ?? new Error("Request failed after retries");
}

export function useApiGet<T>(
  url: string | null,
  opts: UseApiOptions = {},
): UseApiState<T> & { refetch: () => void } {
  const options = { ...DEFAULT_OPTIONS, ...opts };
  const [state, setState] = useState<UseApiState<T>>({ data: null, error: null, isLoading: !!url });
  const abortRef = useRef<AbortController | null>(null);

  const execute = useCallback(async () => {
    if (!url) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setState({ data: null, error: null, isLoading: true });

    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("sb_token") : null;
      const headers: HeadersInit = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const response = await fetchWithRetry(url, { signal: controller.signal, headers }, options.retries!, options.retryDelayMs!);
      const json = (await response.json()) as APIResponse<T>;

      if (json.error) {
        setState({ data: null, error: json.error.message, isLoading: false });
      } else {
        setState({ data: json.data, error: null, isLoading: false });
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setState({ data: null, error: (err as Error).message, isLoading: false });
      }
    }
  }, [url, options.retries, options.retryDelayMs]);

  useEffect(() => {
    execute();
    return () => abortRef.current?.abort();
  }, [execute]);

  return { ...state, refetch: execute };
}

export function useApiPost<T, B = unknown>(
  url: string,
  opts: UseApiOptions = {},
): UseApiState<T> & { execute: (body: B) => Promise<T | null> } {
  const options = { ...DEFAULT_OPTIONS, ...opts };
  const [state, setState] = useState<UseApiState<T>>({ data: null, error: null, isLoading: false });

  const execute = useCallback(async (body: B): Promise<T | null> => {
    setState({ data: null, error: null, isLoading: true });

    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("sb_token") : null;
      const reqHeaders: HeadersInit = { "Content-Type": "application/json" };
      if (token) reqHeaders["Authorization"] = `Bearer ${token}`;
      const response = await fetchWithRetry(url, {
        method: "POST",
        headers: reqHeaders,
        body: JSON.stringify(body),
      }, options.retries!, options.retryDelayMs!);

      const json = (await response.json()) as APIResponse<T>;

      if (json.error) {
        setState({ data: null, error: json.error.message, isLoading: false });
        return null;
      }

      setState({ data: json.data, error: null, isLoading: false });
      return json.data;
    } catch (err) {
      setState({ data: null, error: (err as Error).message, isLoading: false });
      return null;
    }
  }, [url, options.retries, options.retryDelayMs]);

  return { ...state, execute };
}
