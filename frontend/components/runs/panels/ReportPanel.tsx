"use client";

import { useMemo, useState } from "react";
import toast from "react-hot-toast";

import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError } from "@/lib/api";
import { Report } from "@/lib/citations";
import { downloadExport } from "@/lib/download";
import { formatCost, formatDuration, formatNumber } from "@/lib/format";
import { citedSources, markerResolution } from "@/lib/runReport";
import type { ResearchPackage, RunGraph } from "@/lib/types";

import { Hash, runTotals } from "../primitives";

/**
 * The report, read as a report.
 *
 * It used to render as `whitespace-pre-wrap` plain text — every heading a literal `#`,
 * every table a row of pipes, and, far worse, **every citation inert**. `lib/citations.tsx`
 * turns `[n]` into a chip carrying the source and the verbatim snippet behind it, and
 * renders a visible ⚠ for a marker that resolves to nothing. On this surface none of that
 * happened, so a report with a broken citation looked exactly like one without.
 *
 * Reusing that renderer rather than writing a second one is the point: two renderers for
 * the product's central claim is the "two homes for one rule" failure the repo keeps
 * paying for, and the second home never gets the fix.
 */
export function ReportPanel({ graph }: { graph: RunGraph }) {
  const { latest } = runTotals(graph);
  const [busy, setBusy] = useState<"md" | "pdf" | null>(null);

  const sources = useMemo(() => citedSources(graph), [graph]);
  const resolution = useMemo(
    () => (latest ? markerResolution(latest.report_markdown, sources) : null),
    [latest, sources],
  );

  if (!latest) {
    return (
      <EmptyState
        title="No report yet"
        description="This run has not produced a revision. Anything gathered so far is on the Evidence tab."
      />
    );
  }

  if (latest.research_package) {
    return (
      <ResearchFindings
        researchPackage={latest.research_package}
        runId={graph.run.id}
        version={latest.version}
      />
    );
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(latest.report_markdown);
      toast.success("Report copied to clipboard.");
    } catch {
      toast.error("Couldn't access the clipboard.");
    }
  };

  const download = async (format: "md" | "pdf") => {
    setBusy(format);
    try {
      await downloadExport(
        `/runs/${graph.run.id}/export.${format}`,
        `research-${graph.run.id.slice(0, 8)}.${format}`,
      );
    } catch (err) {
      toast.error(
        err instanceof ApiError
          ? err.message
          : `Couldn't export the ${format === "md" ? "Markdown" : "PDF"}.`,
      );
    } finally {
      setBusy(null);
    }
  };

  const tokens = graph.run.tokens_input + graph.run.tokens_output;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          {graph.revisions.length > 1 && (
            <p className="text-xs text-text-secondary">
              Revision {latest.version} of {graph.revisions.length}. Earlier revisions are
              kept unchanged — a rework adds a version, it never overwrites one.
            </p>
          )}
          {resolution && (
            <p
              className={`mt-0.5 text-xs ${
                resolution.unresolved > 0 ? "text-warning" : "text-text-secondary"
              }`}
            >
              {resolution.unresolved === 0
                ? `All ${resolution.total} citation markers in this text resolve to a cited source.`
                : `${resolution.unresolved} of ${resolution.total} citation markers in this text resolve to nothing — each is marked ⚠ below.`}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap gap-2 print:hidden">
          <button type="button" onClick={copy} className="btn btn-secondary" disabled={busy !== null}>
            Copy
          </button>
          <button
            type="button"
            onClick={() => download("md")}
            className="btn btn-secondary"
            disabled={busy !== null}
          >
            {busy === "md" && <span className="spinner" />}
            Download .md
          </button>
          <button
            type="button"
            onClick={() => download("pdf")}
            className="btn btn-secondary"
            disabled={busy !== null}
          >
            {busy === "pdf" && <span className="spinner" />}
            Download PDF
          </button>
        </div>
      </div>

      <article className="card">
        <Report markdown={latest.report_markdown} sources={sources} />
      </article>

      <dl className="flex flex-wrap gap-x-8 gap-y-2 border-t border-border pt-3 text-xs">
        <div>
          <dt className="font-mono text-[length:var(--text-micro)] uppercase tracking-wider text-text-muted">
            Report hash
          </dt>
          <dd className="mt-0.5">
            <Hash value={latest.report_hash} label="Report hash" />
          </dd>
        </div>
        <div>
          <dt className="font-mono text-[length:var(--text-micro)] uppercase tracking-wider text-text-muted">
            Evidence watermark
          </dt>
          <dd
            className="mt-0.5 font-mono tabular-nums text-text-secondary"
            title="The last evidence sequence visible when this revision was written. A threshold, not a count."
          >
            {latest.evidence_watermark}
          </dd>
        </div>
        <div>
          <dt className="font-mono text-[length:var(--text-micro)] uppercase tracking-wider text-text-muted">
            Duration
          </dt>
          <dd className="mt-0.5 font-mono tabular-nums text-text-secondary">
            {formatDuration(graph.run.elapsed_seconds)}
          </dd>
        </div>
        <div>
          <dt className="font-mono text-[length:var(--text-micro)] uppercase tracking-wider text-text-muted">
            Cost
          </dt>
          <dd className="mt-0.5 font-mono tabular-nums text-text-secondary">
            {formatCost(graph.run.cost_usd)}
          </dd>
        </div>
        <div>
          <dt className="font-mono text-[length:var(--text-micro)] uppercase tracking-wider text-text-muted">
            Tokens
          </dt>
          <dd className="mt-0.5 font-mono tabular-nums text-text-secondary">
            {formatNumber(tokens)}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function ResearchFindings({
  researchPackage,
  runId,
  version,
}: {
  researchPackage: ResearchPackage;
  runId: string;
  version: number;
}) {
  const s = researchPackage.summary;
  return (
    <div className="space-y-6">
      <div className="card space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Research Findings</h2>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() =>
              downloadExport(
                "/runs/" + runId + "/research-package?revision_version=" + version,
                "research-" + runId.slice(0, 8) + ".json",
              ).catch(() => toast.error("Couldn't export the research package."))
            }
          >
            Download JSON
          </button>
        </div>
        <p className="text-sm text-text-secondary">{researchPackage.research_question}</p>
        <p className="text-xs text-text-secondary">
          {s.questions_planned} questions · {s.nugget_count} nuggets · {s.evidence_count} pieces
          of evidence · {s.answered} answered · {s.partially_answered} partial · {s.conflicting}
          {" "}conflicting · {s.unanswered} unanswered
        </p>
        <p className="text-xs text-text-secondary">
          Confidence: {s.high_confidence} high · {s.medium_confidence} medium · {s.low_confidence} low
        </p>
      </div>
      {["consumer", "company", "category", "culture", ...Object.keys(researchPackage.domains).filter(
        (domain) => !["consumer", "company", "category", "culture"].includes(domain),
      )].map((domain) => {
        const nuggets = researchPackage.domains[domain] ?? [];
        if (!nuggets.length) return null;
        return (
          <section key={domain} className="space-y-3" aria-label={domain + " findings"}>
            <h2 className="text-lg font-semibold capitalize">{domain}</h2>
            {nuggets.map((n) => (
              <article key={n.id} className="card space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-semibold">{n.module}</h3>
                  <span className="text-xs text-text-secondary">{n.status} · {n.confidence ?? "N/A"}</span>
                </div>
                <p className="text-sm font-medium">{n.question}</p>
                <p className="text-sm">{n.answer ?? "Unanswered."}</p>
                {n.confidence_reason && <p className="text-xs text-text-secondary">Why: {n.confidence_reason}</p>}
                {n.caveats.length > 0 && (
                  <p className="text-xs text-text-secondary">Caveats: {n.caveats.join("; ")}</p>
                )}
                {n.evidence.length > 0 && (
                  <details className="text-sm">
                    <summary className="cursor-pointer">
                      {n.evidence.length} supporting source{n.evidence.length === 1 ? "" : "s"}
                    </summary>
                    <ul className="mt-2 space-y-3">
                      {n.evidence.map((e) => (
                        <li key={e.evidence_id} className="border-l-2 border-border pl-3">
                          <blockquote>{e.quote}</blockquote>
                          <a className="break-all text-link underline" href={e.url} target="_blank" rel="noopener noreferrer">
                            {e.source}
                          </a>
                          <p className="text-xs text-text-secondary">
                            {e.source_type} · {e.suitability} suitability · {e.attestation}
                            {e.published ? " · Published " + e.published : ""}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                <p className="font-mono text-[length:var(--text-micro)] text-text-muted">{n.id}</p>
              </article>
            ))}
          </section>
        );
      })}
    </div>
  );
}
