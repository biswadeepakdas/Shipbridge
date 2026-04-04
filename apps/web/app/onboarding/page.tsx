/** Onboarding wizard — name → framework → stack config → first assessment. */

"use client";

import { useCallback, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { T, FONT } from "@/styles/tokens";
import ScoreArc from "@/components/ui/score-arc";
import { apiUrl } from "@/lib/api";

const FRAMEWORKS = [
  { id: "langraph", name: "LangGraph", desc: "Graph-based agent orchestration" },
  { id: "crewai", name: "CrewAI", desc: "Multi-agent crew collaboration" },
  { id: "autogen", name: "AutoGen", desc: "Microsoft multi-agent conversations" },
  { id: "n8n", name: "n8n", desc: "Workflow automation platform" },
  { id: "custom", name: "Custom", desc: "Custom agent framework" },
];

// Framework-specific default stack configurations for realistic assessments
const FRAMEWORK_STACKS: Record<string, Record<string, unknown>> = {
  langraph: {
    models: ["claude-sonnet-4", "claude-haiku-4-5"],
    tools: ["knowledge_base_search", "api_caller", "data_retriever"],
    deployment: "railway",
    auth: { type: "jwt", provider: "supabase" },
    injection_guard: true,
    user_input: true,
    ci_grader: true,
    test_coverage: 72,
    eval_baseline: true,
    audit_trail: true,
    hitl_gates: true,
    owner: "team@company.com",
    semantic_cache: true,
    token_budget: true,
  },
  crewai: {
    models: ["claude-sonnet-4", "claude-haiku-4-5", "gpt-4o-mini"],
    tools: ["web_search", "file_reader", "email_sender", "slack_notify"],
    deployment: "railway",
    auth: { type: "api_key", provider: "custom" },
    user_input: true,
    ci_grader: true,
    test_coverage: 65,
    eval_baseline: true,
    audit_trail: true,
    hitl_gates: true,
    owner: "ops@company.com",
    semantic_cache: true,
    token_budget: true,
  },
  autogen: {
    models: ["gpt-4o", "gpt-4o-mini"],
    tools: ["code_executor", "web_browser", "file_manager"],
    deployment: "railway",
    auth: { type: "oauth2", provider: "github" },
    injection_guard: true,
    user_input: true,
    mcp_endpoints: ["/tools/code", "/tools/browser"],
    mcp_auth: true,
    test_coverage: 45,
    owner: "dev@company.com",
  },
  n8n: {
    models: ["claude-haiku-4-5"],
    tools: ["slack_bot", "notion_reader", "google_calendar", "email_processor"],
    deployment: "docker",
    auth: { type: "basic", provider: "n8n" },
    user_input: true,
    test_coverage: 30,
    audit_trail: true,
    owner: "ops@company.com",
  },
  custom: {
    models: ["gpt-4o"],
    tools: ["web_browser", "code_executor"],
    deployment: "docker",
    user_input: true,
    mcp_endpoints: ["/tools/browser", "/tools/code"],
    test_coverage: 20,
  },
};

// Module-level variants
const STEP_VARIANTS = {
  enter: { opacity: 0, x: 40 },
  center: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -40 },
};

type Step = 1 | 2 | 3 | 4;

export default function OnboardingPage() {
  const [step, setStep] = useState<Step>(1);
  const [projectName, setProjectName] = useState("");
  const [framework, setFramework] = useState("");
  const [score, setScore] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canAdvance = useMemo(() => {
    if (step === 1) return projectName.trim().length > 0;
    if (step === 2) return framework.length > 0;
    return true;
  }, [step, projectName, framework]);

  const [isAssessing, setIsAssessing] = useState(false);

  const handleNext = useCallback(async () => {
    setError(null);
    if (step === 3) {
      setIsAssessing(true);
      try {
        const token = typeof window !== "undefined" ? localStorage.getItem("sb_token") : null;
        const headers: HeadersInit = { "Content-Type": "application/json" };
        if (token) headers["Authorization"] = `Bearer ${token}`;

        // Create project
        const createRes = await fetch(apiUrl("/api/v1/projects"), {
          method: "POST",
          headers,
          body: JSON.stringify({ name: projectName, framework, stack_json: FRAMEWORK_STACKS[framework] ?? {} }),
        });
        const createJson = await createRes.json();
        const projectId = createJson.data?.id;

        if (projectId) {
          // Trigger assessment
          const assessRes = await fetch(apiUrl(`/api/v1/projects/${projectId}/assess`), {
            method: "POST",
            headers,
          });
          const assessJson = await assessRes.json();
          if (assessJson.data?.total_score !== undefined) {
            setScore(assessJson.data.total_score);
          } else {
            setError("Assessment failed. Please try again.");
            return;
          }
        } else {
          setError(createJson.error?.message ?? "Failed to create project. Please sign in first.");
          return;
        }
      } catch {
        setError("Connection failed. Please check your network and try again.");
        return;
      } finally {
        setIsAssessing(false);
      }
      setStep(4);
    } else if (step < 4) {
      setStep((s) => (s + 1) as Step);
    }
  }, [step, projectName, framework]);

  const handleBack = useCallback(() => {
    if (step > 1) setStep((s) => (s - 1) as Step);
  }, [step]);

  return (
    <div style={{
      minHeight: "100vh", backgroundColor: T.s0, display: "flex",
      flexDirection: "column", alignItems: "center", justifyContent: "center",
      padding: "40px 20px",
    }}>
      {/* Header */}
      <div style={{ textAlign: "center", marginBottom: 40 }}>
        <h1 style={{ fontFamily: FONT.ui, fontSize: 24, fontWeight: 600, color: T.sig, margin: 0 }}>
          ShipBridge
        </h1>
        <p style={{ fontFamily: FONT.ui, fontSize: 14, color: T.t2, marginTop: 4 }}>
          Step {step} of 4
        </p>
      </div>

      {/* Progress bar */}
      <div style={{ width: 320, height: 3, backgroundColor: T.b1, borderRadius: 2, marginBottom: 32 }}>
        <div style={{ width: `${(step / 4) * 100}%`, height: "100%", backgroundColor: T.sig, borderRadius: 2, transition: "width 0.3s ease" }} />
      </div>

      {/* Error display */}
      {error && (
        <div style={{
          width: 400, padding: "10px 16px", marginBottom: 16, borderRadius: 6,
          backgroundColor: "rgba(196,74,74,0.1)", border: "1px solid rgba(196,74,74,0.3)",
          fontFamily: FONT.ui, fontSize: 13, color: T.danger,
        }}>
          {error}
        </div>
      )}

      {/* Step content */}
      <div style={{ width: 400, minHeight: 280 }}>
        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            variants={STEP_VARIANTS}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.25 }}
          >
            {step === 1 && (
              <div>
                <h2 style={{ fontFamily: FONT.ui, fontSize: 18, fontWeight: 600, color: T.t1, marginBottom: 8 }}>
                  Name your project
                </h2>
                <p style={{ fontFamily: FONT.ui, fontSize: 13, color: T.t3, marginBottom: 20 }}>
                  What do you call your AI agent system?
                </p>
                <input
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="e.g., Customer Support Agent"
                  style={{
                    width: "100%", padding: "12px 16px", borderRadius: 6,
                    border: `1px solid ${T.b2}`, backgroundColor: T.s2,
                    color: T.t1, fontFamily: FONT.ui, fontSize: 14, outline: "none",
                  }}
                />
              </div>
            )}

            {step === 2 && (
              <div>
                <h2 style={{ fontFamily: FONT.ui, fontSize: 18, fontWeight: 600, color: T.t1, marginBottom: 8 }}>
                  Select framework
                </h2>
                <p style={{ fontFamily: FONT.ui, fontSize: 13, color: T.t3, marginBottom: 20 }}>
                  Which agent framework are you using?
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {FRAMEWORKS.map((fw) => (
                    <button
                      key={fw.id}
                      type="button"
                      onClick={() => setFramework(fw.id)}
                      style={{
                        padding: "12px 16px", borderRadius: 6, textAlign: "left",
                        border: `1px solid ${framework === fw.id ? T.sig : T.b1}`,
                        backgroundColor: framework === fw.id ? T.sigDim : T.s2,
                        color: T.t1, cursor: "pointer",
                      }}
                    >
                      <div style={{ fontFamily: FONT.ui, fontSize: 13, fontWeight: 500 }}>{fw.name}</div>
                      <div style={{ fontFamily: FONT.ui, fontSize: 11, color: T.t3, marginTop: 2 }}>{fw.desc}</div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {step === 3 && (
              <div>
                <h2 style={{ fontFamily: FONT.ui, fontSize: 18, fontWeight: 600, color: T.t1, marginBottom: 8 }}>
                  Configure stack
                </h2>
                <p style={{ fontFamily: FONT.ui, fontSize: 13, color: T.t3, marginBottom: 20 }}>
                  We&apos;ve pre-filled a configuration for {FRAMEWORKS.find((f) => f.id === framework)?.name ?? "your framework"}.
                  You can customize this later.
                </p>
                <div style={{
                  padding: 16, backgroundColor: T.s2, borderRadius: 8,
                  border: `1px solid ${T.b0}`, fontFamily: FONT.data, fontSize: 12, color: T.t2,
                }}>
                  <div>Project: <span style={{ color: T.t1 }}>{projectName}</span></div>
                  <div>Framework: <span style={{ color: T.sig }}>{framework}</span></div>
                  <div style={{ marginTop: 8, color: T.t3 }}>Click &quot;Run Assessment&quot; to score your project.</div>
                </div>
              </div>
            )}

            {step === 4 && score !== null && (
              <div style={{ textAlign: "center" }}>
                <h2 style={{ fontFamily: FONT.ui, fontSize: 18, fontWeight: 600, color: T.t1, marginBottom: 16 }}>
                  Your first assessment
                </h2>
                <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}>
                  <ScoreArc score={score} size={160} />
                </div>
                <p style={{ fontFamily: FONT.ui, fontSize: 14, color: T.t2, marginBottom: 8 }}>
                  {score >= 75 ? "Your project is ready for production!" : `Score ${score}/100 — address the gap report to reach 75.`}
                </p>
                <p style={{ fontFamily: FONT.ui, fontSize: 12, color: T.t3 }}>
                  Head to the dashboard to explore your results.
                </p>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Navigation buttons */}
      <div style={{ display: "flex", gap: 12, marginTop: 32 }}>
        {step > 1 && step < 4 && (
          <button type="button" onClick={handleBack} style={{
            padding: "10px 24px", borderRadius: 6, border: `1px solid ${T.b2}`,
            backgroundColor: "transparent", color: T.t2, fontFamily: FONT.ui,
            fontSize: 13, cursor: "pointer",
          }}>
            Back
          </button>
        )}
        {step < 4 && (
          <button
            type="button"
            onClick={handleNext}
            disabled={!canAdvance}
            style={{
              padding: "10px 24px", borderRadius: 6, border: "none",
              backgroundColor: canAdvance ? T.sig : T.s3,
              color: canAdvance ? T.s0 : T.t4, fontFamily: FONT.ui,
              fontSize: 13, fontWeight: 500, cursor: canAdvance ? "pointer" : "not-allowed",
            }}
          >
            {isAssessing ? "Assessing..." : step === 3 ? "Run Assessment" : "Continue"}
          </button>
        )}
        {step === 4 && (
          <a href="/dashboard" style={{
            padding: "10px 24px", borderRadius: 6, border: "none",
            backgroundColor: T.sig, color: T.s0, fontFamily: FONT.ui,
            fontSize: 13, fontWeight: 500, textDecoration: "none",
            display: "inline-block",
          }}>
            Go to Dashboard
          </a>
        )}
      </div>
    </div>
  );
}
