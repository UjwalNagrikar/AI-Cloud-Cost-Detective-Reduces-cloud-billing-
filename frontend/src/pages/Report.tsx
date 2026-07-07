import {
  ShieldAlert,
  TrendingDown,
  AlertTriangle,
  CircleCheck,
  AlertCircle,
  Lightbulb,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { fetchAnalysis } from "../api";
import type { AnalysisRecord, Issue } from "../types";

// ── Severity types ────────────────────────────────────────────────────────────

type NormalizedSeverity = "high" | "medium" | "low";

// ── Severity config ───────────────────────────────────────────────────────────

const severityConfig: Record<
  NormalizedSeverity,
  {
    label: string;
    badgeClass: string;
    borderColor: string;
    Icon: typeof AlertCircle;
  }
> = {
  high: {
    label: "High",
    badgeClass: "badge-high",
    borderColor: "rgba(239,68,68,0.4)",
    Icon: AlertCircle,
  },
  medium: {
    label: "Medium",
    badgeClass: "badge-medium",
    borderColor: "rgba(245,158,11,0.4)",
    Icon: AlertTriangle,
  },
  low: {
    label: "Low",
    badgeClass: "badge-low",
    borderColor: "rgba(34,197,94,0.4)",
    Icon: CircleCheck,
  },
};

// ── Severity normalizer ───────────────────────────────────────────────────────

function normalizeSeverity(severity: unknown): NormalizedSeverity {
  const value = String(severity ?? "")
    .trim()
    .toLowerCase();

  switch (value) {
    case "critical":
    case "error":
    case "danger":
    case "severe":
    case "high":
      return "high";

    case "warning":
    case "warn":
    case "moderate":
    case "medium":
      return "medium";

    case "info":
    case "informational":
    case "minor":
    case "low":
      return "low";

    default:
      console.warn(
        `[Report] Unknown severity "${String(
          severity
        )}". Falling back to "low".`
      );

      return "low";
  }
}

// ── Safe value helper ─────────────────────────────────────────────────────────

function safeText(value: unknown, fallback: string): string {
  if (value === null || value === undefined) {
    return fallback;
  }

  const text = String(value).trim();

  return text || fallback;
}

// ── Issue card ────────────────────────────────────────────────────────────────

function IssueCard({
  issue,
  index,
}: {
  issue: Issue;
  index: number;
}) {
  const severity = normalizeSeverity(issue?.severity);

  const config =
    severityConfig[severity] ??
    severityConfig.low;

  const {
    badgeClass,
    borderColor,
    Icon,
    label,
  } = config;

  const resourceName = safeText(
    issue?.resource_name,
    "Unknown resource"
  );

  const issueName = safeText(
    issue?.issue,
    "Optimization issue detected"
  );

  const suggestion = safeText(
    issue?.suggestion,
    "Review this Azure resource and its current configuration."
  );

  const solution = safeText(
    issue?.solution,
    "No optimization strategy was provided for this resource."
  );

  const estimatedSavings = safeText(
    issue?.estimated_monthly_savings,
    "Not estimated"
  );

  return (
    <article
      className="rounded-2xl p-5 animate-fade-up"
      style={{
        background: "rgba(6,15,30,0.7)",
        border: "1px solid rgba(26,53,87,0.8)",
        borderLeft: `3px solid ${borderColor}`,
        animationDelay: `${index * 60}ms`,
      }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <Icon
            size={18}
            className="mt-0.5 shrink-0 text-slate-500"
          />

          <div className="min-w-0">
            <h3 className="font-semibold text-slate-100 text-[15px] truncate">
              {resourceName}
            </h3>

            <p className="text-xs text-slate-500 mt-0.5">
              {issueName}
            </p>
          </div>
        </div>

        <span
          className={`inline-flex items-center px-2.5 py-1 rounded-lg text-[11px] font-semibold uppercase tracking-wider ${badgeClass}`}
        >
          {label}
        </span>
      </div>

      <p className="mt-3 text-sm leading-6 text-slate-400">
        {suggestion}
      </p>

      <div
        className="mt-3 flex items-center gap-2 px-3 py-2 rounded-lg"
        style={{
          background: "rgba(34,197,94,0.05)",
          border: "1px solid rgba(34,197,94,0.15)",
        }}
      >
        <TrendingDown
          size={13}
          className="text-good shrink-0"
        />

        <span className="text-xs text-slate-400">
          Estimated savings:
        </span>

        <span className="text-xs font-semibold text-good">
          {estimatedSavings}
        </span>
      </div>

      {/* ── Optimization Strategy Box ─────────────────────────────── */}

      <div
        className="mt-3 rounded-lg p-3 text-sm leading-6 text-slate-300"
        style={{
          background: "rgba(0, 212, 255, 0.04)",
          border: "1px solid rgba(0, 212, 255, 0.1)",
        }}
      >
        <div className="flex items-center gap-2 mb-1">
          <Lightbulb
            size={13}
            className="text-signal shrink-0"
          />

          <span className="text-xs font-semibold text-signal uppercase tracking-widest">
            Optimization Strategy
          </span>
        </div>

        <p className="text-sm text-slate-400 leading-relaxed">
          {solution}
        </p>
      </div>
    </article>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  color = "text-white",
  glow,
}: {
  label: string;
  value: string | number;
  color?: string;
  glow?: string;
}) {
  return (
    <div
      className="rounded-xl p-4"
      style={{
        background: "rgba(13,31,54,0.6)",
        border: "1px solid rgba(26,53,87,0.9)",
        boxShadow: glow
          ? `inset 0 0 20px ${glow}`
          : undefined,
      }}
    >
      <p className="text-xs font-medium text-slate-500 uppercase tracking-widest">
        {label}
      </p>

      <p className={`stat-value mt-2 ${color}`}>
        {value}
      </p>
    </div>
  );
}

// ── Report page ───────────────────────────────────────────────────────────────

export default function Report() {
  const { id } = useParams();
  const location = useLocation();

  const [analysis, setAnalysis] =
    useState<AnalysisRecord | null>(
      (
        location.state as {
          analysis?: AnalysisRecord;
        } | null
      )?.analysis ?? null
    );

  const [error, setError] = useState("");

  useEffect(() => {
    if (!id || analysis) {
      return;
    }

    fetchAnalysis(id)
      .then((data) => {
        console.log("[Report] Analysis response:", data);

        setAnalysis(data);
      })
      .catch((err) => {
        console.error(
          "[Report] Failed to load analysis:",
          err
        );

        setError(
          err instanceof Error
            ? err.message
            : "Unable to load report."
        );
      });
  }, [id, analysis]);

  if (error) {
    return (
      <div className="alert-error">
        {error}
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="flex items-center gap-3 text-slate-500 text-sm">
        <div className="h-4 w-4 rounded-full border-2 border-signal border-t-transparent animate-spin" />

        Loading report...
      </div>
    );
  }

  const result = analysis.analysis_result;

  const issues = Array.isArray(result?.issues)
    ? result.issues
    : [];

  const highCount = issues.filter(
    (issue) =>
      normalizeSeverity(issue?.severity) === "high"
  ).length;

  const medCount = issues.filter(
    (issue) =>
      normalizeSeverity(issue?.severity) === "medium"
  ).length;

  const lowCount = issues.filter(
    (issue) =>
      normalizeSeverity(issue?.severity) === "low"
  ).length;

  const monthlySavings =
    analysis?.estimated_savings?.monthly ?? 0;

  const currency =
    analysis?.estimated_savings?.currency ?? "USD";

  return (
    <div className="space-y-6">
      {/* ── Hero savings banner ───────────────────────────────────── */}

      <div
        className="rounded-2xl p-6 relative overflow-hidden animate-fade-up"
        style={{
          background:
            "linear-gradient(135deg, rgba(6,15,30,0.95) 0%, rgba(13,31,54,0.95) 100%)",
          border: "1px solid rgba(0,212,255,0.18)",
          boxShadow:
            "0 0 60px rgba(0,212,255,0.06)",
        }}
      >
        <div
          className="absolute -top-12 -right-12 h-48 w-48 rounded-full pointer-events-none"
          style={{
            background: "rgba(0,212,255,0.06)",
            filter: "blur(40px)",
          }}
        />

        <div className="relative">
          <div className="flex items-start gap-4">
            <div
              className="h-11 w-11 rounded-xl flex items-center justify-center shrink-0"
              style={{
                background:
                  "rgba(245,158,11,0.12)",
                border:
                  "1px solid rgba(245,158,11,0.25)",
              }}
            >
              <ShieldAlert
                size={20}
                className="text-warn"
              />
            </div>

            <div className="min-w-0">
              <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest">
                Analysis ·{" "}
                {safeText(
                  analysis.resource_group,
                  "Unknown resource group"
                )}
              </p>

              <h1 className="text-2xl font-bold font-display text-white mt-0.5 tracking-tight">
                Report Complete
              </h1>
            </div>

            <div className="ml-auto text-right shrink-0">
              <p className="text-[11px] font-semibold text-slate-600 uppercase tracking-widest">
                Est. Savings
              </p>

              <p
                className="text-3xl font-bold font-display mt-1"
                style={{
                  background:
                    "linear-gradient(135deg, #22c55e, #86efac)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  backgroundClip: "text",
                }}
              >
                ${monthlySavings} {currency}
              </p>

              <p className="text-[10px] text-slate-600">
                per month
              </p>
            </div>
          </div>

          {/* ── Dynamic Summary ───────────────────────────────────── */}

          <p className="mt-4 text-sm leading-7 text-slate-400">
            Scanned{" "}
            <span className="text-slate-200 font-medium">
              {analysis.resources_scanned ?? 0} resources
            </span>{" "}
            and identified{" "}
            <span className="text-signal font-medium">
              {analysis.issues_found ?? issues.length}{" "}
              optimization opportunities
            </span>{" "}
            to reduce your Azure billing.
          </p>

          {/* ── Stat bar ──────────────────────────────────────────── */}

          <div className="mt-5 grid grid-cols-3 gap-3">
            <StatCard
              label="Resources"
              value={analysis.resources_scanned ?? 0}
            />

            <StatCard
              label="Issues"
              value={
                analysis.issues_found ??
                issues.length
              }
              color="text-warn"
              glow="rgba(245,158,11,0.05)"
            />

            <StatCard
              label="Savings"
              value={`$${monthlySavings}`}
              color="text-good"
              glow="rgba(34,197,94,0.05)"
            />
          </div>

          {/* ── Severity breakdown ────────────────────────────────── */}

          {issues.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {highCount > 0 && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold badge-high">
                  <AlertCircle size={11} />

                  {highCount} High
                </span>
              )}

              {medCount > 0 && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold badge-medium">
                  <AlertTriangle size={11} />

                  {medCount} Medium
                </span>
              )}

              {lowCount > 0 && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold badge-low">
                  <CircleCheck size={11} />

                  {lowCount} Low
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Issue cards ───────────────────────────────────────────── */}

      <div className="space-y-4">
        {issues.length === 0 ? (
          <div
            className="rounded-2xl p-8 text-center"
            style={{
              background: "rgba(34,197,94,0.04)",
              border:
                "1px solid rgba(34,197,94,0.12)",
            }}
          >
            <CircleCheck
              size={32}
              className="text-good mx-auto mb-3"
            />

            <p className="text-sm font-medium text-good">
              No issues detected
            </p>

            <p className="text-xs text-slate-600 mt-1">
              This resource group looks well-optimised.
            </p>
          </div>
        ) : (
          issues.map((issue, index) => (
            <IssueCard
              key={`${safeText(
                issue?.resource_name,
                "resource"
              )}-${index}`}
              issue={issue}
              index={index}
            />
          ))
        )}
      </div>
    </div>
  );
}