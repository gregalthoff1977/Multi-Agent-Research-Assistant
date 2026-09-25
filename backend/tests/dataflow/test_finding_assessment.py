"""Claim-dependent evidence judgment, with no network or model in the decision."""

import re

from langchain_core.messages import AIMessage

from research_engine.findings import assess_source, build_findings, evidence_id
from research_engine.graph import (
    _apply_finding_confidence,
    _claim_scope_grounded,
    _market_scope_block,
    _remove_uncited_claims,
)
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


async def test_report_qualifies_weak_claims_and_removes_unsupported_claims(monkeypatch):
    from research_engine import graph

    async def judged(pairs):
        return ["ritual" in snippet.lower() for _, snippet in pairs], 0.001, 10, 2

    monkeypatch.setattr(graph, "_verifier_verdicts", judged)
    evidence = item("https://reddit.com/r/coffee/123", "Someone describes a cold brew ritual.")
    assessed = build_findings([evidence], [task("culture", "ritual")])
    report = (
        "# Report\n\n## Culture\n"
        "A coffee community described a cold brew ritual [1].\n"
        "Most young people drink cold brew daily [2].\n\n"
        "## Sources\n[1] https://reddit.com/r/coffee/123\n"
    )
    result, cost, tokens_in, tokens_out = await _apply_finding_confidence(
        report, assessed, {evidence["source_url"]: 1}
    )
    assert "In one cited cultural account, a coffee community" in result
    assert "Most young people" not in result
    assert "[1] https://reddit.com" in result
    assert (cost, tokens_in, tokens_out) == (0.001, 10, 2)


async def test_same_url_distinct_findings_do_not_launder_consumer_claim(monkeypatch):
    from research_engine import graph

    url = "https://chameleoncoldbrew.com/products"
    product = item(url, "Chameleon sells an organic cold brew concentrate.")
    opinion = item(url, "Chameleon says Gen Z prefers the taste of its coffee.")
    opinion["task_id"] = 2
    assessed = build_findings(
        [product, opinion],
        [
            task("company", "product fact"),
            {**task("consumer", "consumer perception", "Gen Z"), "id": 2},
        ],
    )

    async def judged(pairs):
        return (
            [
                "Gen Z" in snippet if "Gen Z" in claim else "sells" in snippet
                for claim, snippet in pairs
            ],
            0.0,
            0,
            0,
        )

    monkeypatch.setattr(graph, "_verifier_verdicts", judged)
    report = "Chameleon sells concentrate [1].\nGen Z prefers the taste [1].\n"
    output, *_ = await _apply_finding_confidence(report, assessed, {url: 1})
    assert "Chameleon sells concentrate [1]" in output
    assert "Gen Z prefers the taste" not in output


async def test_failed_finding_alignment_removes_claim(monkeypatch):
    from research_engine import graph

    source = item("https://chameleoncoldbrew.com/products", "Chameleon sells concentrate.")
    assessed = build_findings([source], [task("company", "product fact")])

    async def unavailable(pairs):
        raise RuntimeError("critic unavailable")

    monkeypatch.setattr(graph, "_verifier_verdicts", unavailable)
    assert (
        await _apply_finding_confidence(
            "Chameleon sells concentrate [1].", assessed, {source["source_url"]: 1}
        )
    )[0] == ""


def test_market_scopes_are_explicit_and_not_corroboration():
    tasks = [
        {
            **task("category", "market size", "U.S. cold-brew coffee market", "U.S."),
            "id": 2,
            "time_period": "2024",
        },
        {
            **task("category", "market size", "RTD cold-brew market", "global"),
            "id": 3,
            "time_period": "2025",
        },
    ]
    sources = [
        {
            **item("https://market-a.com/report", "U.S. cold brew was USD 244.69 Million in 2024."),
            "task_id": 2,
        },
        {
            **item("https://market-b.com/report", "RTD cold brew was US$ 1.56 Billion in 2025."),
            "task_id": 3,
        },
    ]
    assessed = build_findings(sources, tasks)
    assert len(assessed) == 2
    assert all(f["confidence"] == "low" for f in assessed)
    assert all(f["independent_publishers"] == 0 for f in assessed)
    assert assessed[0]["scope_comparisons"][0]["relation"] == "different_task_scope"
    assert "different or unverified" in " ".join(assessed[1]["caveats"])
    block = _market_scope_block(
        assessed, {sources[0]["source_url"]: 1, sources[1]["source_url"]: 2}
    )
    assert "[1] concerns U.S. cold-brew coffee market (U.S., 2024)" in block
    assert "[2] concerns RTD cold-brew market (global, 2025)" in block
    assert "cannot be compared as equivalent" in block


def test_uncited_factual_prose_cannot_survive_failed_repair():
    report = "# Report\n\nEveryone prefers cold brew.\nChameleon sells concentrate [1].\n"
    assert "Everyone prefers" not in _remove_uncited_claims(report)
    assert "Chameleon sells concentrate [1]" in _remove_uncited_claims(report)


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

    async def verified(sid, draft, sources, verified_single_quotes=None):
        return draft, 0.0, 0, 0

    async def judged(pairs):
        return [True] * len(pairs), 0.0, 0, 0

    monkeypatch.setattr(graph, "get_llm", lambda role: Stub())
    monkeypatch.setattr(graph, "_verify_citation_fidelity", verified)
    monkeypatch.setattr(graph, "_verifier_verdicts", judged)
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
    assert "In one cited cultural account, a vendor" in result["draft_report"]
    assert result["judgment_applied"] is True
    assert [s["url"] for s in result["sources"]] == [good["source_url"], weak["source_url"]]


async def test_commercial_consumer_gap_cannot_be_cited_as_gen_z_fact(monkeypatch):
    from research_engine import graph

    vendor = item(
        "https://commonwealthjoe.com/blogs/blog/sip-snap-share-gen-z-and-cold-brew-culture",
        "Gen Z drinkers choose cold brew for healthy habits and late-night study sessions.",
    )
    prompts_seen = []

    class Stub:
        async def ainvoke(self, messages):
            prompts_seen.append(messages[-1].content)
            return AIMessage(content="# Consumer\nGen Z chooses cold brew for study sessions [1].")

    monkeypatch.setattr(graph, "get_llm", lambda role: Stub())
    token = set_run_config(RunConfig(llm_mode="real"))
    try:
        outcome = await graph.synthesizer_node(
            {
                "session_id": "s",
                "original_query": "Why cold brew?",
                "evidence": [vendor],
                "tasks": [task("consumer", "motivation", "Gen Z coffee drinkers", "U.S.")],
                "cost_usd": 0.0,
                "tokens_input": 0,
                "tokens_output": 0,
            }
        )
    finally:
        reset_run_config(token)
    assert outcome["findings"][0]["status"] == "research_gap"
    assert outcome["sources"] == []
    assert vendor["snippet"] not in prompts_seen[0]
    assert "Gen Z chooses" not in outcome["draft_report"]


def test_vendor_demographic_superlative_never_becomes_a_measured_fact():
    source = item(
        "https://pureearthcoffee.com/blogs/fuel-your-pursuit/gen-z-coffee-consumption-habits-2026",
        "Gen Z is the fastest-growing coffee demographic in the United States.",
    )
    demographic = build_findings(
        [source], [task("consumer", "demographic growth", "Gen Z", "U.S.")]
    )[0]
    cultural = build_findings([source], [task("culture", "emerging signal", "Gen Z", "U.S.")])[0]
    assert demographic["status"] == cultural["status"] == "research_gap"
    assert cultural["evidence_role"] == "measured_fact"
    assert cultural["source_assessments"][0]["source_class"] == "commercial_blog"
    assert not _claim_scope_grounded(
        "Gen Z is the largest and fastest-growing coffee demographic in the U.S. [1].",
        source["snippet"],
    )


def test_accio_population_statistic_needs_a_method():
    source = item(
        "https://www.accio.com/business/new_trending_coffee",
        "Certifications are critical for 59% of consumers.",
    )
    finding = build_findings(
        [source], [task("category", "industry observation", "U.S. consumers", "U.S.")]
    )[0]
    assert finding["evidence_role"] == "measured_fact"
    assert finding["status"] == "research_gap"
    assert finding["source_assessments"][0]["source_class"] == "commercial_vendor"
    assert finding["source_assessments"][0]["methodology"] == "unverified"


async def test_precision_from_unknown_publisher_is_attributed_and_caveated(monkeypatch):
    from research_engine import graph

    source = item(
        "https://glassandnote.com/beer/pricing-product-analysis-iced-rtd-coffee-drinks-the-us",
        "Price elasticity is −0.32 for premium cold-brew formats.",
    )
    assessed = build_findings([source], [task("category", "pricing", "U.S. cold brew", "U.S.")])
    finding = assessed[0]
    assert finding["evidence_role"] == "measured_fact"
    assert finding["status"] == "qualified"
    assert finding["confidence"] == "low"
    assert finding["finding"] != source["snippet"]
    assert finding["source_quotes"] == [source["snippet"]]
    assert "method and sample" in " ".join(finding["caveats"])

    async def judged(pairs):
        return [True] * len(pairs), 0.0, 0, 0

    monkeypatch.setattr(graph, "_verifier_verdicts", judged)
    draft = "Price elasticity is −0.32 for premium cold-brew formats [1]."
    result, *_ = await _apply_finding_confidence(draft, assessed, {source["source_url"]: 1})
    assert "glassandnote.com reports, without a verified method, that price elasticity" in result


async def test_cultural_occurrence_survives_but_population_claim_does_not(monkeypatch):
    from research_engine import graph

    source = item(
        "https://commonwealthjoe.com/blogs/blog/coffee-that-connects",
        "Gen Z share cold brew online; our brand presents it with visual garnishes.",
    )
    assessed = build_findings([source], [task("culture", "aesthetic signal", "Gen Z")])
    assert assessed[0]["status"] == "emerging_signal"

    async def judged(pairs):
        return [True] * len(pairs), 0.0, 0, 0

    monkeypatch.setattr(graph, "_verifier_verdicts", judged)
    draft = "A coffee brand presents cold brew with visual garnishes [1].\nGen Z share cold brew online [1]."
    result, *_ = await _apply_finding_confidence(draft, assessed, {source["source_url"]: 1})
    assert "In one cited cultural account, a coffee brand" in result
    assert "Gen Z share cold brew" not in result


def test_scope_expansion_is_blocked():
    pairs = [
        ("Cold brew appeals to consumers [1].", "Iced coffee appeals to consumers."),
        ("Younger consumers choose coffee [1].", "Gen Z chooses coffee."),
        ("RTD cold brew grew [1].", "RTD coffee grew."),
        ("The U.S. RTD coffee market grew [1].", "The global RTD coffee market grew."),
    ]
    assert all(not _claim_scope_grounded(claim, quote) for claim, quote in pairs)


def test_real_finalizer_refuses_a_draft_without_judgment():
    from research_engine.graph import finalizer_node

    token = set_run_config(RunConfig(llm_mode="real"))
    try:
        rejected = finalizer_node(
            {"tasks": [task("consumer", "behavior")], "draft_report": "An unassessed fact [1]."}
        )
        accepted = finalizer_node(
            {
                "tasks": [task("consumer", "behavior")],
                "judgment_applied": True,
                "draft_report": "Assessed fact [1].",
            }
        )
    finally:
        reset_run_config(token)
    assert rejected["final_report"] is None and rejected["error"]
    assert accepted["final_report"] == "Assessed fact [1]."


async def test_one_url_with_many_findings_only_checks_relevant_quote(monkeypatch):
    from research_engine import graph

    url = "https://chameleoncoldbrew.com/products"
    sources = [
        {**item(url, f"Chameleon sells concentrate flavor {n}."), "task_id": n}
        for n in range(1, 11)
    ]
    tasks = [{**task("company", "product fact"), "id": n} for n in range(1, 11)]
    assessed = build_findings(sources, tasks)
    seen_pairs = []

    async def judged(pairs):
        seen_pairs.extend(pairs)
        return [True] * len(pairs), 0.0, 0, 0

    monkeypatch.setattr(graph, "_verifier_verdicts", judged)
    result, *_ = await _apply_finding_confidence(
        "Chameleon sells concentrate flavor 7 [1].", assessed, {url: 1}
    )
    assert result == "Chameleon sells concentrate flavor 7 [1]."
    assert len(seen_pairs) == 1
    assert seen_pairs[0][1] == sources[6]["snippet"]


async def test_verified_single_quote_and_evidence_id_reuse_prior_ruling(monkeypatch):
    from research_engine import graph

    source = item("https://chameleoncoldbrew.com/products", "Chameleon sells concentrate.")
    assessed = build_findings([source], [task("company", "product fact")])
    assert assessed[0]["evidence_ids"] == [evidence_id(source["source_url"], source["snippet"])]
    calls = 0

    async def judged(pairs):
        nonlocal calls
        calls += 1
        return [True] * len(pairs), 0.0, 0, 0

    monkeypatch.setattr(graph, "_verifier_verdicts", judged)
    draft = "Chameleon sells concentrate [1]."
    validated = {}
    verified, *_ = await graph._verify_citation_fidelity(
        "s",
        draft,
        [{"index": 1, "url": source["source_url"], "snippets": [source["snippet"]]}],
        validated,
    )
    result, *_ = await _apply_finding_confidence(
        verified, assessed, {source["source_url"]: 1}, validated
    )
    assert validated == {draft: source["snippet"]}
    assert result == draft
    assert calls == 1  # citation verifier did the semantic work once


async def test_duplicate_claim_quote_pair_is_verified_only_once(monkeypatch):
    from research_engine import graph

    source = item("https://chameleoncoldbrew.com/products", "Chameleon sells concentrate.")
    assessed = build_findings([source], [task("company", "product fact")])
    seen = []

    async def judged(pairs):
        seen.extend(pairs)
        return [True] * len(pairs), 0.0, 0, 0

    monkeypatch.setattr(graph, "_verifier_verdicts", judged)
    claim = "Chameleon sells concentrate [1]."
    result, *_ = await _apply_finding_confidence(
        claim + "\n" + claim, assessed, {source["source_url"]: 1}
    )
    assert result == claim + "\n" + claim
    assert seen == [(claim, source["snippet"])]


async def test_same_attested_quote_in_multiple_findings_is_one_semantic_pair(monkeypatch):
    from research_engine import graph

    source = item("https://chameleoncoldbrew.com/products", "Chameleon sells concentrate.")
    assessed = build_findings([source], [task("company", "product fact")])
    # Legacy finding snapshots can repeat a quotation with a different judgment.
    assessed.append({**assessed[0], "status": "qualified", "confidence": "low"})
    assert len(assessed) == 2
    pairs_checked = []

    async def judged(pairs):
        pairs_checked.extend(pairs)
        return [True] * len(pairs), 0.0, 0, 0

    monkeypatch.setattr(graph, "_verifier_verdicts", judged)
    report, *_ = await _apply_finding_confidence(
        "Chameleon sells concentrate [1].", assessed, {source["source_url"]: 1}
    )
    assert pairs_checked == [("Chameleon sells concentrate [1].", source["snippet"])]
    assert "According to chameleoncoldbrew.com" in report


async def test_citation_to_one_url_cannot_use_other_urls_quote(monkeypatch):
    from research_engine import graph

    first = item("https://example.org/concentrate", "Chameleon sells concentrate.")
    second = item("https://example.org/rtd", "Chameleon sells RTD coffee.")
    assessed = build_findings([first], [task("company", "product fact")])
    finding = assessed[0]
    finding["source_urls"].append(second["source_url"])
    finding["source_quotes"].append(second["snippet"])
    finding["evidence_ids"].append(evidence_id(second["source_url"], second["snippet"]))

    async def judged(pairs):
        raise AssertionError("Other URL's quotation cannot reach the model")

    monkeypatch.setattr(graph, "_verifier_verdicts", judged)
    result, *_ = await _apply_finding_confidence(
        "Chameleon sells RTD coffee [1].",
        assessed,
        {first["source_url"]: 1, second["source_url"]: 2},
    )
    assert result == ""


async def test_mismatched_scope_and_number_never_reach_semantic_verifier(monkeypatch):
    from research_engine import graph

    source = item("https://glassandnote.com/analysis", "Global iced coffee sales rose 8%.")
    assessed = build_findings([source], [task("category", "market size")])

    async def judged(pairs):
        raise AssertionError("scope and number mismatches must not reach the model")

    monkeypatch.setattr(graph, "_verifier_verdicts", judged)
    draft = "U.S. cold brew sales rose 8% [1].\nGlobal iced coffee sales rose 18% [1]."
    result, *_ = await _apply_finding_confidence(draft, assessed, {source["source_url"]: 1})
    assert "rose" not in result


async def test_alignment_work_scales_with_selected_quotes_not_url_cartesian_product(
    monkeypatch,
):
    from research_engine import graph

    # 30 claims, 6 URLs, 8 attested quotations per URL. The old algorithm sent
    # 30 * 8 = 240 pairs / 60 sequential model calls. Exact numeric grounding
    # leaves one quotation per cited claim and 8 model batches of four.
    items = []
    tasks = []
    for url_number in range(6):
        for quote_number in range(8):
            task_id = url_number * 8 + quote_number + 1
            url = f"https://university-{url_number}.edu/study"
            items.append(
                {
                    **item(url, f"Survey estimates {100 + task_id}% for format {task_id}."),
                    "task_id": task_id,
                }
            )
            tasks.append({**task("category", "quantitative incidence"), "id": task_id})
    assessed = build_findings(items, tasks)
    draft = "\n".join(
        f"Survey estimates {100 + n}% for format {n} [{(n - 1) // 8 + 1}]." for n in range(1, 31)
    )

    class Verifier:
        calls = 0

        async def ainvoke(self, messages):
            self.calls += 1
            count = len(re.findall(r"^Claim \d+:", messages[-1].content, re.M))
            return AIMessage(content="\n".join(f"Claim {i}: YES" for i in range(1, count + 1)))

    model = Verifier()
    events = []

    class Logged:
        def info(self, event, **fields):
            events.append((event, fields))

        def warning(self, *args, **kwargs):
            raise AssertionError("No model or alignment warning expected")

    monkeypatch.setattr(graph, "get_llm", lambda role: model)
    monkeypatch.setattr(graph, "logger", Logged())
    result, *_ = await _apply_finding_confidence(
        draft, assessed, {f"https://university-{n}.edu/study": n + 1 for n in range(6)}
    )
    summary = dict(events)["finding_alignment_summary"]
    assert result.count("survey estimates") == 30
    assert summary["cited_claims"] == 30
    assert summary["candidate_findings_considered"] == 240
    assert summary["eliminated_deterministically"] == 210
    assert summary["semantic_pairs"] == 30
    assert summary["verifier_batches"] == model.calls == 8
    assert len([event for event, _ in events if event == "citation_verifier_batch_started"]) == 8
    assert summary["claims_accepted_unchanged"] == summary["claims_removed"] == 0
    assert summary["claims_qualified"] == 30
