/** Login / Signup page — create account or sign in. */

"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { T, FONT } from "@/styles/tokens";
import { apiUrl } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [tenantName, setTenantName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !fullName.trim()) return;

    setIsLoading(true);
    setError(null);

    try {
      const slug = (tenantName || fullName).toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 30);
      const res = await fetch(apiUrl("/api/v1/auth/signup"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          full_name: fullName.trim(),
          tenant_name: tenantName.trim() || `${fullName.trim()}'s Workspace`,
          tenant_slug: slug,
        }),
      });

      const json = await res.json();

      if (json.error) {
        setError(json.error.message);
        return;
      }

      // Store auth data
      if (json.data?.access_token) {
        localStorage.setItem("sb_token", json.data.access_token);
      }
      if (json.data?.tenant) {
        localStorage.setItem("sb_tenant", JSON.stringify(json.data.tenant));
      }

      router.push("/dashboard");
    } catch (err) {
      setError("Connection failed. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }, [email, fullName, tenantName, router]);

  const inputStyle = {
    width: "100%",
    padding: "12px 14px",
    borderRadius: "8px",
    border: `1px solid ${T.b1}`,
    backgroundColor: T.s2,
    color: T.t1,
    fontFamily: FONT.ui,
    fontSize: 14,
    outline: "none",
    boxSizing: "border-box" as const,
  };

  const labelStyle = {
    fontFamily: FONT.label,
    fontSize: 10,
    color: T.t3,
    textTransform: "uppercase" as const,
    letterSpacing: "0.06em",
    display: "block",
    marginBottom: 6,
  };

  return (
    <div style={{
      minHeight: "100vh",
      backgroundColor: T.s0,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "24px",
    }}>
      <div style={{
        width: "100%",
        maxWidth: 400,
        backgroundColor: T.s1,
        borderRadius: "12px",
        border: `1px solid ${T.b0}`,
        padding: "40px 32px",
      }}>
        {/* Logo / Title */}
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <h1 style={{
            fontFamily: FONT.label,
            fontSize: 24,
            fontWeight: 600,
            color: T.sig,
            margin: 0,
            letterSpacing: "0.04em",
          }}>
            ShipBridge
          </h1>
          <p style={{
            fontFamily: FONT.ui,
            fontSize: 13,
            color: T.t3,
            marginTop: 8,
          }}>
            Pilot-to-Production for AI Agents
          </p>
        </div>

        {/* Error */}
        {error && (
          <div style={{
            padding: "10px 14px",
            marginBottom: 16,
            borderRadius: "6px",
            backgroundColor: T.dangerDim,
            border: `1px solid ${T.danger}`,
            fontFamily: FONT.ui,
            fontSize: 13,
            color: T.danger,
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Full Name</label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Jane Doe"
              required
              style={inputStyle}
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="jane@company.com"
              required
              style={inputStyle}
            />
          </div>

          <div style={{ marginBottom: 24 }}>
            <label style={labelStyle}>Workspace Name <span style={{ color: T.t4 }}>(optional)</span></label>
            <input
              type="text"
              value={tenantName}
              onChange={(e) => setTenantName(e.target.value)}
              placeholder="My Team"
              style={inputStyle}
            />
          </div>

          <button
            type="submit"
            disabled={isLoading || !email.trim() || !fullName.trim()}
            style={{
              width: "100%",
              padding: "12px",
              borderRadius: "8px",
              border: "none",
              backgroundColor: (!email.trim() || !fullName.trim()) ? T.s3 : T.sig,
              color: (!email.trim() || !fullName.trim()) ? T.t3 : T.s0,
              fontFamily: FONT.ui,
              fontSize: 14,
              fontWeight: 600,
              cursor: (!email.trim() || !fullName.trim()) ? "default" : "pointer",
              opacity: isLoading ? 0.6 : 1,
              transition: "opacity 0.15s",
            }}
          >
            {isLoading ? "Signing in..." : "Get Started"}
          </button>
        </form>
      </div>
    </div>
  );
}
