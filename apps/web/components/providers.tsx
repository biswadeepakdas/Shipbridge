"use client";

import { TenantProvider } from "@/hooks/use-current-tenant";

export default function Providers({ children }: { children: React.ReactNode }) {
  return <TenantProvider>{children}</TenantProvider>;
}
