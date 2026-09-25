"""Versioned research nuggets derived from assessed, attested evidence.

The package is the run's research result. Markdown is only a deterministic human
rendering needed by older review, export and indexing contracts.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from research_engine import findings

VERSION = 1
DOMAINS = ("consumer", "company", "category", "culture")
ROLES = {
    "measured_fact": "MEASURED_FACT",
    "observed_behavior": "OBSERVED_BEHAVIOR",
    "consumer_perception": "CONSUMER_PERCEPTION",
    "company_fact": "COMPANY_CLAIM",
    "company_interpretation": "COMPANY_CLAIM",
    "category_observation": "INDUSTRY_INTERPRETATION",
    "cultural_signal": "CULTURAL_SIGNAL",
    "anecdotal_signal": "ANECDOTAL_SIGNAL",
}


def _identifier(task: dict, evidence_ids: list[str], ordinal: int) -> str:
    domain = re.sub(r"[^A-Z0-9]+", "-", str(task.get("domain") or "OTHER").upper()).strip("-")
    module = re.sub(r"[^A-Z0-9]+", "-", str(task.get("module") or "OTHER").upper()).strip("-")
    task_id = re.sub(r"[^A-Za-z0-9-]+", "-", str(task.get("id") or ordinal))
    anchor = "|".join(sorted(evidence_ids)) if evidence_ids else "UNANSWERED"
    suffix = hashlib.sha256(anchor.encode()).hexdigest()[:8].upper()
    return f"{domain}-{module}-{task_id}-{suffix}"


def _reason(finding: dict) -> str:
    assessments = finding["source_assessments"]
    publishers = finding["independent_publishers"]
    if finding["status"] == "emerging_signal":
        return "A cultural occurrence is attested; its prevalence is not established."
    if finding["confidence"] == "high":
        if finding["evidence_role"] == "company_fact":
            return "A primary company source directly establishes this company fact."
        return f"{publishers} independent direct sources support the stated scope."
    if finding["confidence"] == "medium":
        return (
            f"{publishers} direct source(s) support the claim; independent corroboration "
            "or scope is limited."
        )
    if any(a["methodology"] == "unverified" for a in assessments):
        return "The cited assertion has no verified measurement method or sample."
    return "Available evidence is limited in authority, directness, or independent support."


def _consolidate_conflicts(matches: list[dict], contradictions: list[dict]) -> list[dict]:
    """Keep the rival answers and their quotes together for a disputed question."""
    disputed = [f for f in matches if any("directly disagree" in c for c in f["caveats"])]
    if len(disputed) < 2:
        return matches
    urls = {url for f in disputed for url in f["source_urls"]}
    if not any(
        pair.get("source_a") in urls and pair.get("source_b") in urls for pair in contradictions
    ):
        return matches
    combined = dict(disputed[0])
    combined["finding"] = "Sources report conflicting answers: " + "; ".join(
        f["finding"] for f in disputed
    )
    for key in ("source_quotes", "evidence_ids", "source_urls", "source_assessments"):
        combined[key] = [value for finding in disputed for value in finding[key]]
    combined["caveats"] = list(dict.fromkeys(c for f in disputed for c in f["caveats"]))
    combined["confidence"] = "low"
    return [combined, *(f for f in matches if f not in disputed)]


def _answers_task(finding: dict, task: dict) -> bool:
    """A product listing cannot answer a consumer behavior question by association."""
    if (task.get("domain") or "").lower() != "consumer":
        return True
    quotes = " ".join(finding["source_quotes"]).lower()
    company_offering = re.search(r"\b(sells?|offers?|stocks?|launched|produces?)\b", quotes)
    consumer_action = re.search(
        r"\b(consumers?|respondents?|drinkers?|buyers?|purchasers?|gen z|millennials?)\b",
        quotes,
    )
    return not (company_offering and not consumer_action)


def build_nuggets(
    tasks: list[dict], evidence: list[dict], contradictions: list[dict] | None = None
) -> list[dict]:
    """One answer per distinct attested proposition, plus gaps for every missed task."""
    # A search-result excerpt proves only that a search result appeared, not the
    # underlying claim. Unchecked and unattested snippets cannot answer questions.
    eligible = [
        e
        for e in evidence
        if e.get("attestation_grade") in {"FETCHED_BODY", "CORPUS_DOCUMENT"}
        and not e.get("snippet_unverified")
        and (e.get("snippet") or "").strip()
    ]
    assessed = findings.build_findings(eligible, tasks, contradictions, allow_task_reuse=True)
    raw_by_id = {findings.evidence_id(e["source_url"], e["snippet"].strip()): e for e in eligible}
    by_task: dict[str, list[dict]] = defaultdict(list)
    for finding in assessed:
        by_task[finding["task_id"]].append(finding)

    nuggets: list[dict] = []
    for ordinal, task in enumerate(tasks, 1):
        task_id = str(task.get("id"))
        matches = [
            f
            for f in by_task.get(task_id, [])
            if f["status"] != "research_gap" and _answers_task(f, task)
        ]
        matches = _consolidate_conflicts(matches, contradictions or [])
        if not matches:
            matches = [None]
        for finding in matches:
            supports = []
            if finding and finding["status"] != "research_gap":
                for evidence_id, quote, url, assessment in zip(
                    finding["evidence_ids"],
                    finding["source_quotes"],
                    finding["source_urls"],
                    finding["source_assessments"],
                    strict=True,
                ):
                    raw = raw_by_id.get(evidence_id)
                    if not raw or raw["snippet"].strip() != quote or raw["source_url"] != url:
                        continue
                    if assessment["suitability"] == "unsuitable":
                        continue
                    supports.append(
                        {
                            "evidence_id": evidence_id,
                            "quote": quote,
                            "source": raw.get("source_title") or assessment["publisher"],
                            "url": url,
                            "source_type": assessment["source_class"].upper(),
                            "published": raw.get("published") or raw.get("publication_date"),
                            "attestation": assessment["attestation"],
                            "suitability": assessment["suitability"].upper(),
                            "suitability_reason": assessment["reason"],
                            "geography_fit": assessment["geography_fit"],
                            "population_fit": assessment["population_fit"],
                            "methodology": assessment["methodology"],
                        }
                    )
            has_answer = bool(supports)
            status = (
                "CONFLICTING"
                if has_answer
                and finding
                and any("directly disagree" in c for c in finding["caveats"])
                else "ANSWERED"
                if has_answer and finding and finding["status"] == "established"
                else "PARTIALLY_ANSWERED"
                if has_answer
                else "UNANSWERED"
            )
            caveats = list(finding["caveats"]) if finding else []
            if not has_answer:
                caveats.append("No sufficiently reliable attested evidence was found.")
            scope = {
                key: str(task.get(key) or "") for key in ("geography", "population", "time_period")
            }
            nuggets.append(
                {
                    "id": _identifier(task, [e["evidence_id"] for e in supports], ordinal),
                    "domain": str(task.get("domain") or "unclassified").lower(),
                    "module": task.get("module") or "Unclassified",
                    "task_id": task_id,
                    "question": task.get("query") or task.get("evidence_type") or "",
                    "answer": finding["finding"] if has_answer else None,
                    "evidence_type": ROLES.get(finding["evidence_role"], "ANECDOTAL_SIGNAL")
                    if has_answer
                    else None,
                    "confidence": finding["confidence"].upper() if has_answer else None,
                    "confidence_reason": _reason(finding) if has_answer else None,
                    "scope": scope,
                    "evidence": supports,
                    "evidence_ids": [e["evidence_id"] for e in supports],
                    "caveats": list(dict.fromkeys(caveats)),
                    "status": status,
                }
            )
    return nuggets


def package(question: str, nuggets: list[dict], contradictions: list[dict] | None = None) -> dict:
    """Derived counts and Four Cs navigation; nuggets are the stored revision snapshot."""
    summary = {
        "questions_planned": len({n["task_id"] for n in nuggets}),
        "nugget_count": len(nuggets),
        "evidence_count": len({e["evidence_id"] for n in nuggets for e in n["evidence"]}),
    }
    for status in ("ANSWERED", "PARTIALLY_ANSWERED", "CONFLICTING", "UNANSWERED"):
        summary[status.lower()] = sum(n["status"] == status for n in nuggets)
    for level in ("HIGH", "MEDIUM", "LOW"):
        summary[f"{level.lower()}_confidence"] = sum(n["confidence"] == level for n in nuggets)
    domains = dict.fromkeys(DOMAINS, [])
    for domain in sorted({n["domain"] for n in nuggets} - set(DOMAINS)):
        domains[domain] = []
    return {
        "version": VERSION,
        "research_question": question,
        "summary": summary,
        "domains": {domain: [n for n in nuggets if n["domain"] == domain] for domain in domains},
        "contradictions": contradictions or [],
        "research_gaps": [n["id"] for n in nuggets if n["status"] == "UNANSWERED"],
    }


def render_markdown(result: dict) -> str:
    """Compatibility view, mechanically derived from the package without new claims."""
    lines = ["# Research Findings", "", f"Question: {result['research_question']}", ""]
    for domain, nuggets in result["domains"].items():
        if not nuggets:
            continue
        lines.extend([f"## {domain.title()}", ""])
        for n in nuggets:
            lines.extend(
                [
                    f"### {n['module']} — {n['id']}",
                    "",
                    f"**Question:** {n['question']}",
                    "",
                    f"**Status:** {n['status']} · **Confidence:** {n['confidence'] or 'N/A'}",
                    "",
                    f"**Answer:** {n['answer'] or 'Unanswered.'}",
                    "",
                ]
            )
            if n["confidence_reason"]:
                lines.extend([f"**Why:** {n['confidence_reason']}", ""])
            for e in n["evidence"]:
                lines.extend([f"- Evidence: {e['quote']} ({e['url']})", ""])
            if n["caveats"]:
                lines.extend(["**Caveats:** " + "; ".join(n["caveats"]), ""])
    return "\n".join(lines).strip() + "\n"
