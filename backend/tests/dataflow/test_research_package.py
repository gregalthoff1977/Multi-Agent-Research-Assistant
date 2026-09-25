"""The new run result is task answers with inspectable, attested evidence."""

import json

import pytest

from research_engine.research_package import build_nuggets, package, render_markdown


def task(task_id=1, domain="company", **overrides):
    return {
        "id": task_id,
        "domain": domain,
        "module": "Product" if domain == "company" else "Behaviors",
        "query": "What is established by the source?",
        "evidence_type": "product fact" if domain == "company" else "observed behavior",
        "population": "Chameleon Cold-Brew" if domain == "company" else "Gen Z",
        "geography": "U.S.",
        **overrides,
    }


def evidence(task_id=1, url="https://chameleoncoldbrew.com/products", **overrides):
    return {
        "task_id": task_id,
        "source_url": url,
        "source_title": "Product listing",
        "snippet": "Chameleon Cold-Brew sells organic concentrate in the U.S.",
        "attestation_grade": "FETCHED_BODY",
        **overrides,
    }


def test_each_task_has_nugget_even_when_only_other_tasks_have_evidence():
    nuggets = build_nuggets([task(1), task(2, domain="consumer")], [evidence()])
    assert {n["task_id"] for n in nuggets} == {"1", "2"}
    assert nuggets[0]["status"] == "ANSWERED"
    assert nuggets[0]["confidence"] == "HIGH"
    assert nuggets[0]["confidence_reason"]
    assert nuggets[0]["evidence_type"] == "COMPANY_CLAIM"
    assert nuggets[0]["evidence"][0]["quote"] == evidence()["snippet"]
    assert nuggets[1]["status"] == "UNANSWERED"
    assert nuggets[1]["answer"] is nuggets[1]["confidence"] is None
    assert nuggets[1]["evidence"] == []


def test_unattested_and_search_only_sources_cannot_answer():
    items = [
        evidence(attestation_grade="SEARCH_SNIPPET"),
        evidence(url="https://other.com", attestation_grade=None),
        evidence(url="https://third.com", snippet_unverified=True),
    ]
    nugget = build_nuggets([task()], items)[0]
    assert nugget["status"] == "UNANSWERED"
    assert nugget["evidence"] == []
    assert "reliable attested evidence" in nugget["caveats"][0]


def test_source_suitability_changes_with_the_question():
    source = evidence(task_id=1)
    company, consumer = build_nuggets(
        [task(1), task(2, domain="consumer")], [source, {**source, "task_id": 2}]
    )
    assert company["status"] == "ANSWERED" and company["confidence"] == "HIGH"
    assert consumer["status"] == "UNANSWERED"


def test_low_confidence_culture_signal_survives_without_prevalence_claim():
    cultural_task = task(1, domain="culture", evidence_type="ritual", population="online coffee")
    social = evidence(
        url="https://reddit.com/r/coffee/123",
        snippet="A member describes making cold brew at home on Sundays.",
    )
    nugget = build_nuggets([cultural_task], [social])[0]
    assert nugget["status"] == "PARTIALLY_ANSWERED"
    assert nugget["confidence"] == "LOW"
    assert nugget["evidence_type"] == "CULTURAL_SIGNAL"
    assert "prevalence" in nugget["confidence_reason"]
    assert "cultural expression" in nugget["answer"]


def test_single_uncorroborated_measurement_remains_qualified():
    measured = task(1, domain="category", evidence_type="market size", population="cold brew")
    vendor = evidence(
        url="https://vendor.com/market",
        snippet="The U.S. cold brew market is $312 million.",
    )
    nugget = build_nuggets([measured], [vendor])[0]
    assert nugget["status"] == "PARTIALLY_ANSWERED"
    assert nugget["confidence"] == "LOW"
    assert nugget["answer"].startswith("vendor.com reports:")
    assert any("method" in caveat.lower() for caveat in nugget["caveats"])


def test_scope_is_explicit_and_unknown_fits_are_not_hidden():
    scoped = task(1, domain="consumer", population="Gen Z", geography="U.S.")
    quote = evidence(
        url="https://university.edu/poll",
        snippet="A survey found people drinking iced coffee.",
    )
    nugget = build_nuggets([scoped], [quote])[0]
    assert nugget["scope"]["population"] == "Gen Z"
    assert nugget["confidence"] != "HIGH"
    assert any("fit is unverified" in caveat for caveat in nugget["caveats"])


def test_two_independent_direct_sources_can_raise_confidence_when_scope_fits():
    scoped = task(1, domain="consumer", population="Gen Z", geography="U.S.")
    quote = "A U.S. survey found Gen Z drinkers choose iced coffee."
    sources = [
        evidence(url="https://college-a.edu/a", snippet=quote, key_fact="Gen Z drinkers choose iced coffee."),
        evidence(
            url="https://college-b.edu/b",
            snippet="A U.S. poll found Gen Z drinkers choose iced coffee.",
            key_fact="Gen Z drinkers choose iced coffee.",
        ),
    ]
    nuggets = build_nuggets([scoped], sources)
    assert len(nuggets) == 1
    assert nuggets[0]["confidence"] == "HIGH"
    assert len(nuggets[0]["evidence"]) == 2
    assert len({e["evidence_id"] for e in nuggets[0]["evidence"]}) == 2


def test_conflicting_sources_preserve_both_answers_and_lineage():
    scoped = task(1, domain="category", evidence_type="market size", population="cold brew")
    a = evidence(url="https://vendor-a.com/a", snippet="U.S. cold brew market is $312 million.")
    b = evidence(url="https://vendor-b.com/b", snippet="U.S. cold brew market is $892 million.")
    conflict = [{"source_a": a["source_url"], "source_b": b["source_url"]}]
    nuggets = build_nuggets([scoped], [a, b], conflict)
    assert len(nuggets) == 1
    assert nuggets[0]["status"] == "CONFLICTING"
    assert len(nuggets[0]["evidence"]) == 2
    assert "$312" in nuggets[0]["answer"] and "$892" in nuggets[0]["answer"]
    assert nuggets[0]["confidence"] == "LOW"


def test_same_quote_can_support_distinct_tasks_without_losing_provenance():
    same = evidence()
    nuggets = build_nuggets([task(1), task(2)], [same, {**same, "task_id": 2}])
    assert all(n["status"] == "ANSWERED" for n in nuggets)
    assert nuggets[0]["evidence_ids"] == nuggets[1]["evidence_ids"]
    assert nuggets[0]["id"] != nuggets[1]["id"]


def test_json_round_trip_keeps_stable_identifiers_and_deterministic_totals():
    tasks = [task(1), task(2, domain="culture")]
    nuggets = build_nuggets(tasks, [evidence()])
    result = package("Cold brew?", nuggets)
    copy = json.loads(json.dumps(result))
    assert copy == result
    assert copy["domains"]["company"][0]["id"] == build_nuggets(tasks, [evidence()])[0]["id"]
    assert copy["summary"]["questions_planned"] == 2
    assert copy["summary"]["answered"] == 1
    assert copy["summary"]["unanswered"] == 1
    assert copy["summary"]["evidence_count"] == 1
    assert "Chameleon Cold-Brew sells organic" in render_markdown(result)


def test_unclassified_legacy_tasks_remain_visible_in_package():
    nuggets = build_nuggets([task(domain=None)], [])
    result = package("General research?", nuggets)
    assert result["domains"]["unclassified"] == nuggets
    assert "General research?" in render_markdown(result)


async def test_package_path_never_calls_narrative_synthesizer(monkeypatch):
    from research_engine import graph
    from research_engine.runconfig import RunConfig, reset_run_config, set_run_config

    def forbidden(*args, **kwargs):
        raise AssertionError("package output must never generate prose")

    monkeypatch.setattr(graph, "get_llm", forbidden)
    token = set_run_config(RunConfig(output_mode="package", llm_mode="real"))
    try:
        result = await graph.synthesizer_node(
            {"session_id": "test", "original_query": "What is sold?", "tasks": [task()], "evidence": [evidence()], "contradictions": []}
        )
    finally:
        reset_run_config(token)
    assert result["research_package"]["summary"]["answered"] == 1
    assert result["judgment_applied"] is True
    assert result["findings"][0]["evidence"][0]["attestation"] == "FETCHED_BODY"


async def test_model_attempt_and_stage_duration_are_logged_even_on_failure(monkeypatch):
    from research_engine import graph
    from research_engine.runconfig import RunConfig, reset_run_config, set_run_config

    records = []

    class Capture:
        def info(self, event, **fields):
            records.append((event, fields))

    async def failing(state):
        async def provider():
            raise RuntimeError("provider unavailable")

        await graph._logged_model_call("executor", provider())

    monkeypatch.setattr(graph, "logger", Capture())
    token = set_run_config(RunConfig(output_mode="package", llm_mode="real"))
    try:
        with pytest.raises(RuntimeError, match="provider unavailable"):
            await graph._timed_node("executor", failing)({"session_id": "run-1"})
    finally:
        reset_run_config(token)
    assert [(event, fields["stage"]) for event, fields in records] == [
        ("research_model_call", "executor"),
        ("research_stage_summary", "executor"),
    ]
    assert all(fields["elapsed_ms"] >= 0 for _, fields in records)
