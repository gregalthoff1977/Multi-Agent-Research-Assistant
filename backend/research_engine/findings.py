"""Conservative, claim-dependent assessment of attested research evidence.

This layer does not infer survey methods, publication dates, or independent reporting
from a URL. Unknown dimensions stay unknown; repetition by vendors never raises confidence.
Findings express what a quotation can establish; raw quotations remain separate.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from urllib.parse import urlsplit

from pydantic import BaseModel, Field


class SourceAssessment(BaseModel):
    source_class: str
    suitability: str  # strong | limited | signal | unsuitable
    reason: str
    attestation: str
    publisher: str
    geography_fit: str = "unverified"
    population_fit: str = "unverified"
    recency: str = "unverified"
    methodology: str = "unverified"


class Finding(BaseModel):
    finding: str
    source_quotes: list[str] = Field(default_factory=list)
    domain: str
    module: str
    task_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    evidence_role: str
    status: str  # established | qualified | emerging_signal | research_gap
    confidence: str  # high | medium | low
    caveats: list[str] = Field(default_factory=list)
    source_assessments: list[SourceAssessment] = Field(default_factory=list)
    independent_publishers: int = 0
    # The research task's intended scope, retained for the strategist and for
    # comparing figures that look alike but measure different markets.
    scope: dict[str, str] = Field(default_factory=dict)
    scope_comparisons: list[dict[str, str]] = Field(default_factory=list)


def _publisher(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""
    # A conservative publisher key, including common second-level country domains.
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "gov", "ac"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _normalized_url(url: str) -> str:
    value = (url or "").strip().rstrip("/").lower()
    if value.startswith("https://"):
        value = value[8:]
    elif value.startswith("http://"):
        value = value[7:]
    return value.removeprefix("www.")


def _tokens(value: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", value.lower()) if len(t) > 3}


def evidence_id(url: str, snippet: str) -> str:
    """Stable across checkpoint and SQL deduplication; includes the attributed URL."""
    return hashlib.sha256(f"{url}\0{snippet}".encode()).hexdigest()


def source_class(url: str, title: str, task: dict) -> str:
    host = _publisher(url)
    if url.startswith("corpus://"):
        return "uploaded_document"
    if not host:
        return "unknown"
    if host.endswith(".gov"):
        return "government"
    if (
        host.endswith(".edu")
        or host.endswith(".ac.uk")
        or host in {"arxiv.org", "pubmed.ncbi.nlm.nih.gov"}
    ):
        return "academic"
    if host in {"reddit.com", "tiktok.com", "instagram.com", "youtube.com", "urbandictionary.com"}:
        return "social_community"
    if host == "accio.com":
        return "commercial_vendor"
    if host in {"wikipedia.org", "linkedin.com", "medium.com", "substack.com"}:
        return "user_published"
    if host in {
        "statista.com",
        "mordorintelligence.com",
        "fortunebusinessinsights.com",
        "grandviewresearch.com",
    }:
        return "syndicated_research"
    if host in {"target.com", "walmart.com", "amazon.com", "kroger.com"}:
        return "retailer"
    if host in {"reuters.com", "apnews.com", "nytimes.com", "wsj.com"}:
        return "journalism"
    # A brand-owned host is identified only for a company task about that brand.
    # Exact domain-label matching avoids treating brand-fan.example as the company.
    # Publisher identity still warrants human review; no DNS ownership claim is made.
    if task.get("domain") == "company":
        brand = task.get("population") or ""
        brand_label = "".join(re.findall(r"[a-z0-9]+", brand.lower()))
        if brand_label and brand_label == host.split(".")[0]:
            return "primary_company"
    if "/blog" in url.lower() or "blog" in title.lower():
        return "commercial_blog"
    return "unknown"


def _role(task: dict, snippet: str = "") -> str:
    domain = (task.get("domain") or "").lower()
    kind = (task.get("evidence_type") or "").lower()
    quote = snippet.lower()
    # A task's Culture or Pricing label must not turn a population estimate or
    # elasticity into a mere occurrence. The assertion itself determines its role.
    if domain != "company" and (
        re.search(r"\d+(?:\.\d+)?\s*%", quote)
        or (domain == "category" and re.search(r"\b(elasticit\w*|cogs|cost of goods)\b", quote))
        or (domain == "culture" and re.search(r"\b(largest|fastest.growing|majority)\b", quote))
    ):
        return "measured_fact"
    if domain == "culture":
        return "cultural_signal"
    if domain == "company":
        if any(
            t in kind
            for t in ("audience", "perception", "motivation", "behavior", "interpretation")
        ):
            return "company_interpretation"
        return "company_fact"
    if any(t in kind for t in ("percentage", "incidence", "quantitative", "market size", "sales")):
        return "measured_fact"
    if any(t in kind for t in ("attitude", "belief", "motivation", "perception")):
        return "consumer_perception"
    if domain == "consumer":
        return "observed_behavior"
    return "category_observation"


def assess_source(evidence: dict, task: dict) -> SourceAssessment:
    url = evidence.get("source_url") or ""
    cls = source_class(url, evidence.get("source_title") or "", task)
    role = _role(task, evidence.get("snippet") or "")
    grade = evidence.get("attestation_grade") or "UNCHECKED"
    snippet = (evidence.get("snippet") or "").lower()
    method = (
        "described"
        if re.search(
            r"\b(survey|sample|respondents|experiment|dataset|interviewed|tracked|poll|observed)\b",
            snippet,
        )
        else "unverified"
    )
    suitability = "limited"
    reason = "Source type or method does not establish this claim independently."
    if grade == "UNCHECKED" or evidence.get("snippet_unverified"):
        suitability, reason = "unsuitable", "Snippet was not attested to retrieved content."
    elif role == "company_fact" and cls == "primary_company":
        suitability, reason = "strong", "Company material directly supports a company fact."
    elif role == "company_fact" and cls == "retailer":
        suitability, reason = "strong", "Retailer listing directly documents an offering."
    elif role == "company_interpretation" and cls == "primary_company":
        suitability, reason = (
            "limited",
            "Company material records its own account, not audience behavior.",
        )
    elif role in {"observed_behavior", "consumer_perception", "measured_fact"}:
        if cls in {"government", "academic"} and method == "described":
            suitability, reason = (
                "strong",
                "The quotation describes a research method; scope still needs checking.",
            )
        elif cls in {"government", "academic"}:
            suitability, reason = (
                "limited",
                "A scholarly host alone does not establish methodology.",
            )
        elif cls == "syndicated_research":
            suitability, reason = (
                "limited",
                "Method and sampled population are not verified from a source label.",
            )
        elif cls in {
            "primary_company",
            "commercial_blog",
            "commercial_vendor",
            "social_community",
            "user_published",
        }:
            suitability, reason = (
                "unsuitable",
                "This source cannot establish population behavior or incidence.",
            )
    elif role == "cultural_signal" and cls in {
        "social_community",
        "user_published",
        "commercial_blog",
    }:
        suitability, reason = (
            "signal",
            "An observed expression can indicate a signal, not its prevalence.",
        )
    elif cls in {"government", "academic"}:
        suitability, reason = "strong", "Direct institutional evidence, subject to scope."
    elif cls == "syndicated_research":
        suitability, reason = "limited", "Methodology and scope need independent verification."
    if grade == "SEARCH_SNIPPET" and suitability == "strong":
        suitability, reason = "limited", "Only a search-result excerpt was retrieved."
    geography = (task.get("geography") or "").lower()
    population = (task.get("population") or "").lower()
    geo_aliases = {
        "u.s.": ("u.s.", "united states", "u.s. ", "american"),
        "us": ("united states", "u.s.", "american"),
    }
    geo_fit = (
        "stated"
        if geography
        and geography not in {"global", "not specified"}
        and any(alias in snippet for alias in geo_aliases.get(geography, (geography,)))
        else "unverified"
    )
    pop_terms = _tokens(population) - {"people", "consumers", "market", "brand", "coffee"}
    generation_fit = "gen z" not in population or "gen z" in snippet
    pop_fit = (
        "stated"
        if generation_fit
        and (
            (pop_terms and all(t in snippet for t in pop_terms))
            or (not pop_terms and "gen z" in population and "gen z" in snippet)
        )
        else "unverified"
    )
    return SourceAssessment(
        source_class=cls,
        suitability=suitability,
        reason=reason,
        attestation=grade,
        publisher=_publisher(url),
        geography_fit=geo_fit,
        population_fit=pop_fit,
        methodology=method,
    )


def _finding_statement(
    members: list[tuple[str, dict, SourceAssessment]], status: str, task: dict
) -> str:
    """A permissible research statement, distinct from its attested quotation."""
    if status == "research_gap":
        return f"Available evidence does not establish: {task.get('query') or task.get('evidence_type') or 'this question'}"
    item = members[0][1]
    snippet = item["snippet"].strip()
    key_fact = (item.get("key_fact") or "").strip()
    # A verbatim substring is safe to use; the executor's free paraphrase is not.
    statement = key_fact if key_fact and key_fact.lower() in snippet.lower() else snippet
    publisher = members[0][2].publisher or "the cited source"
    if status == "emerging_signal":
        return f"The {publisher} material contains this cultural expression: {statement}"
    if status == "qualified":
        return f"{publisher} reports: {statement}"
    return statement


def build_findings(
    evidence: list[dict], tasks: list[dict], contradictions: list[dict] | None = None
) -> list[dict]:
    """Assess exact claims, keeping weak evidence visible without promoting repetition.

    Same-source duplicate snippets are one observation. Different assertions within an
    atomic task remain separate unless their *literal* key facts agree; paraphrase or
    syndication across publishers is never assumed to be independent corroboration.
    """
    by_task = {str(t.get("id")): t for t in tasks}
    contested = {
        _normalized_url(p.get(key))
        for p in (contradictions or [])
        for key in ("source_a", "source_b")
        if p.get(key)
    }
    groups: dict[tuple[str, str, str], list[tuple[str, dict, SourceAssessment]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for item in evidence:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("task_id", ""))
        task = by_task.get(task_id)
        url, snippet = (item.get("source_url") or "").strip(), (item.get("snippet") or "").strip()
        if not task or not url or not snippet or item.get("snippet_unverified"):
            continue
        assessment = assess_source(item, task)
        if assessment.suitability == "unsuitable" and assessment.attestation == "UNCHECKED":
            continue
        identity = (url.lower().rstrip("/"), " ".join(snippet.lower().split()))
        if identity in seen:
            continue
        seen.add(identity)
        key_fact = " ".join((item.get("key_fact") or "").lower().split())
        # Only group model-authored key facts when the complete statement occurs in the
        # attested snippet; otherwise a paraphrase may conflate distinct assertions.
        group_key = (
            key_fact if key_fact and key_fact in " ".join(snippet.lower().split()) else identity[1]
        )
        groups[(task_id, group_key, _role(task, snippet))].append(
            (evidence_id(url, snippet), item, assessment)
        )

    findings = []
    for (task_id, _, role), members in groups.items():
        task = by_task[task_id]
        assessments = [a for _, _, a in members]
        strong_publishers: set[str] = set()
        quoted_texts: set[str] = set()
        repeated_direct = False
        for _, item, assessment in members:
            if assessment.suitability != "strong" or not assessment.publisher:
                continue
            exact = " ".join(item["snippet"].lower().split())
            # Verbatim republication on another host is derivative, not a second
            # observation. Distinct wording is only a proxy, never proof of independence.
            if exact in quoted_texts:
                repeated_direct = True
                continue
            quoted_texts.add(exact)
            strong_publishers.add(assessment.publisher)
        disputed = any(_normalized_url(m.get("source_url")) in contested for _, m, _ in members)
        direct_company = role == "company_fact" and bool(strong_publishers)
        scope_verified = all(
            (
                a.geography_fit == "stated"
                or task.get("geography") in {None, "", "global", "not specified"}
            )
            and (a.population_fit == "stated" or not task.get("population"))
            for a in assessments
        )
        high = not disputed and (direct_company or (len(strong_publishers) >= 2 and scope_verified))
        medium = not disputed and bool(strong_publishers)
        confidence = "high" if high else "medium" if medium else "low"
        status = (
            "established"
            if high
            else "emerging_signal"
            if role == "cultural_signal" and any(a.suitability != "unsuitable" for a in assessments)
            else "qualified"
            if any(a.suitability != "unsuitable" for a in assessments)
            else "research_gap"
        )
        caveats = []
        if disputed:
            caveats.append("Sources directly disagree; the factual conflict is unresolved.")
        if not high and len(strong_publishers) < 2 and not direct_company:
            caveats.append("Independent, direct corroboration is insufficient.")
        if repeated_direct:
            caveats.append("Verbatim repetition across sources is not independent corroboration.")
        if any(a.suitability in {"limited", "signal", "unsuitable"} for a in assessments):
            caveats.append("Source suitability limits what this evidence can establish.")
        if role == "measured_fact" and any(a.methodology == "unverified" for a in assessments):
            caveats.append("The underlying measurement method and sample are unverified.")
        if any(a.attestation == "SEARCH_SNIPPET" for a in assessments):
            caveats.append("At least one quotation was attested only to a search result.")
        if status == "emerging_signal":
            caveats.append("Occurrence does not establish prevalence or representativeness.")
        if any(a.geography_fit == "unverified" for a in assessments) and task.get(
            "geography"
        ) not in {None, "", "global", "not specified"}:
            caveats.append("Geographic fit is unverified in the quotation.")
        if any(a.population_fit == "unverified" for a in assessments) and task.get("population"):
            caveats.append("Population fit is unverified in the quotation.")
        if task.get("freshness"):
            caveats.append("Publication recency is unverified.")
        findings.append(
            Finding(
                finding=_finding_statement(members, status, task),
                source_quotes=[m["snippet"] for _, m, _ in members],
                domain=task.get("domain") or "unclassified",
                module=task.get("module") or "unclassified",
                task_id=task_id,
                evidence_ids=[id_ for id_, _, _ in members],
                source_urls=[m["source_url"] for _, m, _ in members],
                evidence_role=role,
                status=status,
                confidence=confidence,
                caveats=caveats,
                source_assessments=assessments,
                independent_publishers=len(strong_publishers),
                scope={
                    key: str(task.get(key) or "")
                    for key in ("query", "geography", "population", "time_period", "evidence_type")
                },
            ).model_dump()
        )
    # Two category-size estimates must not be counted as independent confirmation
    # merely because they are both prices of a market. Compare their task scopes,
    # without inferring that the definitions supplied by publishers are equivalent.
    sizes = [
        f
        for f in findings
        if f["domain"] == "category"
        and "market size" in f["scope"]["evidence_type"].lower()
        and re.search(
            r"(?:\$|USD).{0,30}(?:\b(?:million|billion)\b|\d+(?:\.\d+)?\s*[mb]\b)",
            f["finding"],
            re.I,
        )
    ]
    for i, left in enumerate(sizes):
        for right in sizes[i + 1 :]:
            dimensions = [
                key
                for key in ("geography", "population", "time_period")
                if left["scope"][key].lower() != right["scope"][key].lower()
            ]
            # Even an identical task description does not establish that two
            # proprietary market forecasts use the same channel or product scope.
            relation = "different_task_scope" if dimensions else "unverified_source_scope"
            for current, other in ((left, right), (right, left)):
                current["scope_comparisons"].append(
                    {
                        "other_task_id": other["task_id"],
                        "other_evidence_id": other["evidence_ids"][0],
                        "relation": relation,
                        "dimensions": ", ".join(dimensions) or "publisher definitions",
                    }
                )
                caution = "Market estimates have different or unverified definitions; do not compare them as equivalent."
                if caution not in current["caveats"]:
                    current["caveats"].append(caution)
    return findings
