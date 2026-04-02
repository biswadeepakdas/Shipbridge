/** Tenant context provider and hook for multi-tenancy. */

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

interface Tenant {
  id: string;
  name: string;
  slug: string;
}

interface AuthState {
  token: string | null;
  tenant: Tenant | null;
  isLoading: boolean;
}

interface TenantContextValue extends AuthState {
  setToken: (token: string) => void;
  setTenant: (tenant: Tenant) => void;
  logout: () => void;
}

const TenantContext = createContext<TenantContextValue | null>(null);

const STORAGE_KEY_TOKEN = "sb_token";
const STORAGE_KEY_TENANT = "sb_tenant";

export function TenantProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    token: null,
    tenant: null,
    isLoading: true,
  });

  // Hydrate from localStorage on mount
  useEffect(() => {
    const token = localStorage.getItem(STORAGE_KEY_TOKEN);
    const tenantJson = localStorage.getItem(STORAGE_KEY_TENANT);
    const tenant = tenantJson ? (JSON.parse(tenantJson) as Tenant) : null;
    setState({ token, tenant, isLoading: false });
  }, []);

  const setToken = useCallback((token: string) => {
    localStorage.setItem(STORAGE_KEY_TOKEN, token);
    setState((prev) => ({ ...prev, token }));
  }, []);

  const setTenant = useCallback((tenant: Tenant) => {
    localStorage.setItem(STORAGE_KEY_TENANT, JSON.stringify(tenant));
    setState((prev) => ({ ...prev, tenant }));
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY_TOKEN);
    localStorage.removeItem(STORAGE_KEY_TENANT);
    setState({ token: null, tenant: null, isLoading: false });
  }, []);

  const value = useMemo(
    () => ({ ...state, setToken, setTenant, logout }),
    [state, setToken, setTenant, logout],
  );

  return (
    <TenantContext.Provider value={value}>{children}</TenantContext.Provider>
  );
}

export function useCurrentTenant(): TenantContextValue {
  const ctx = useContext(TenantContext);
  if (!ctx) {
    throw new Error("useCurrentTenant must be used within a TenantProvider");
  }
  return ctx;
}
