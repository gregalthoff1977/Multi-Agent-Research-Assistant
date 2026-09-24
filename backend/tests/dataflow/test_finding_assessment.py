"""Claim-dependent evidence judgment, with no network or model in the decision."""

from langchain_core.messages import AIMessage

from research_engine.findings import assess_source, build_findings, evidence_id
from research_engine.graph import _apply_finding_confidence
from research_engine.runconfig import RunConfig, reset_run_config, set_run_config


def task(domain, kind, population="Chameleon Cold-Brew", geography="not specified"):
    return {
        "id": 1,
        "domain": domain,
        "module": "Products" if domain == "company" else "Behaviors",
        "evidence_type": kind,
        "population": population,
        "geography": geography,
    }


def item(url, snippet, *, grade="FETCHED_BODY", key_fact=""):
    return {
        "task_id": 1,
        "source_url": url,
        "source_title": "Products",
        "snippet": snippet,
        "key_fact": key_fact,
        "attestation_grade": grade,
    }


def test_company_primary_supports_product_fact_but_not_consumer_behavior():
    source = item(
        "https://chameleoncoldbrew.com/products", "Chameleon sells a cold brew concentrate."
    )
    company = build_findings([source], [task("company", "product fact")])[0]
    assert company["status"] == "established"
    assert company["confidence"] == "high"
    assert company["source_assessments"][0]["source_class"] == "primary_company"

    consumer_task = task("consumer", "observed behavior", "Gen Z coffee drinkers")
    consumer = build_findings([source], [consumer_task])[0]
    assert consumer["confidence"] == "low"
    assert consumer["status"] == "qualified"
    assert assess_source(source, consumer_task).suitability == "limited"


def test_social_source_is_a_signal_not_a_prevalence_measure():
    source = item("https://reddit.com/r/coffee/123", "Someone describes a cold brew ritual.")
    cultural = build_findings([source], [task("culture", "ritual", "online coffee community")])[0]
    assert cultural["status"] == "emerging_signal"
    assert cultural["confidence"] == "low"
    assert "prevalence" in " ".join(cultural["caveats"])
    measured = build_findings([source], [task("consumer", "quantitative incidence")])[0]
    assert measured["status"] == "research_gap"


def test_vendor_repetition_and_one_publisher_never_create_high_confidence():
    sources = [
        item(
            "https://vendor-a.com/blog/post",
            "Young people buy more cold brew.",
            key_fact="Young people buy more cold brew.",
        ),
        item(
            "https://vendor-b.com/blog/post",
            "Young people buy more cold brew.",
            key_fact="Young people buy more cold brew.",
        ),
        item(
            "https://vendor-b.com/blog/copy",
            "Young people buy more cold brew.",
            key_fact="Young people buy more cold brew.",
        ),
    ]
    finding = build_findings(sources, [task("consumer", "observed behavior")])[0]
    assert finding["independent_publishers"] == 0
    assert finding["confidence"] == "low"
    assert finding["status"] == "research_gap"
    assert len(finding["evidence_ids"]) == 3


def test_independent_direct_sources_still_require_population_and_geography_fit():
    claim = "Gen Z coffee drinkers choose cold coffee weekly."
    sources = [
        item("https://university-a.edu/study", "A survey found U.S. " + claim, key_fact=claim),
        item(
            "https://university-b.edu/study",
            "An independent poll found U.S. " + claim,
            key_fact=claim,
        ),
    ]
    scoped = task("consumer", "observed behavior", "Gen Z coffee drinkers", "U.S.")
    finding = build_findings(sources, [scoped])[0]
    assert finding["confidence"] == "high"
    assert finding["independent_publishers"] == 2
    missing_scope = [
        dict(s, snippet="A survey found coffee drinkers choose cold coffee weekly.", key_fact="")
        for s in sources
    ]
    finding = build_findings(missing_scope, [scoped])[0]
    assert finding["confidence"] == "medium"
    assert any("Geographic fit" in caveat for caveat in finding["caveats"])
    repeated = dict(sources[0], source_url="https://university-b.edu/copy")
    copied = build_findings([sources[0], repeated], [scoped])[0]
    assert copied["confidence"] == "medium"
    assert any("Verbatim repetition" in caveat for caveat in copied["caveats"])


def test_unattested_and_duplicate_evidence_do_not_create_findings():
    source = item("https://chameleoncoldbrew.com/products", "Chameleon sells a concentrate.")
    unverified = item("https://other.com", "An invented quotation.")
    unverified["snippet_unverified"] = True
    unchecked = item("https://third.com", "A plausible unverified quote.", grade=None)
    findings = build_findings(
        [source, source.copy(), unverified, unchecked], [task("company", "product fact")]
    )
    assert len(findings) == 1
    assert findings[0]["evidence_ids"] == [evidence_id(source["source_url"], source["snippet"])]


def test_search_result_downgrades_primary_source_and_conflict_caveats_it():
    source = item(
        "https://chameleoncoldbrew.com/products",
        "Chameleon sells concentrate.",
        grade="SEARCH_SNIPPET",
    )
    finding = build_findings([source], [task("company", "product fact")])[0]
    assert finding["confidence"] == "low"
    assert finding["status"] == "qualified"
    assert any("search result" in caveat for caveat in finding["caveats"])
    source["attestation_grade"] = "FETCHED_BODY"
    opposed = build_findings(
        [source],
        [task("company", "product fact")],
        [{"source_a": source["source_url"], "source_b": "https://other.example"}],
    )[0]
    assert opposed["confidence"] == "low"
    assert any("disagree" in caveat for caveat in opposed["caveats"])


def test_report_qualifies_weak_claims_and_removes_unsupported_claims():
    evidence = item("https://reddit.com/r/coffee/123", "Someone describes a cold brew ritual.")
    assessed = build_findings([evidence], [task("culture", "ritual")])
    report = (
        "# Report\n\n## Culture\n"
        "A coffee community described a cold brew ritual [1].\n"
        "Most young people drink cold brew daily [2].\n\n"
        "## Sources\n[1] https://reddit.com/r/coffee/123\n"
    )
    result = _apply_finding_confidence(report, assessed, {evidence["source_url"]: 1})
    assert "Emerging cultural signal: A coffee community" in result
    assert "Most young people" not in result
    assert "[1] https://reddit.com" in result


async def test_real_synthesis_receives_assessed_findings_and_filters_unattested(monkeypatch):
    from research_engine import graph

    good = item("https://chameleoncoldbrew.com/products", "Chameleon sells concentrate.")
    alias = item("http://chameleoncoldbrew.com/products", "Chameleon sells a second product.")
    unchecked = item("https://bad.example/blog", "Everyone drinks it every day.", grade=None)
    weak = item("https://coffee-vendor.com/blog", "A vendor describes a youth coffee ritual.")
    weak["task_id"] = 2
    seen_prompts = []

    class Stub:
        async def ainvoke(self, messages):
            seen_prompts.append(messages[-1].content)
            return AIMessage(
                content=(
                    "# Report\n\n## Company\nChameleon sells concentrate [1].\n\n"
                    "## Culture\nA vendor describes a youth coffee ritual [2].\n\n"
                    "## Sources\n[1] https://chameleoncoldbrew.com/products\n"
                    "[2] https://coffee-vendor.com/blog\n"
                ),
                usage_metadata={"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
            )

    async def verified(sid, draft, sources):
        return draft, 0.0, 0, 0

    monkeypatch.setattr(graph, "get_llm", lambda role: Stub())
    monkeypatch.setattr(graph, "_verify_citation_fidelity", verified)
    token = set_run_config(RunConfig(llm_mode="real"))
    try:
        result = await graph.synthesizer_node(
            {
                "session_id": "s",
                "original_query": "q",
                "evidence": [good, alias, unchecked, weak],
                "tasks": [task("company", "product fact"), {**task("culture", "ritual"), "id": 2}],
                "cost_usd": 0.0,
                "tokens_input": 0,
                "tokens_output": 0,
            }
        )
    finally:
        reset_run_config(token)
    assert "Everyone drinks it" not in seen_prompts[0]
    assert result["findings"][0]["confidence"] == "high"
    assert result["findings"][1]["source_urls"] == [good["source_url"]]
    assert result["findings"][2]["status"] == "emerging_signal"
    assert "Emerging cultural signal: A vendor" in result["draft_report"]
    assert [s["url"] for s in result["sources"]] == [good["source_url"], weak["source_url"]]
