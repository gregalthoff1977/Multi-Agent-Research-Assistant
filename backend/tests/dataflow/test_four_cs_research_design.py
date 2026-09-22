from research_engine import prompts
from research_engine.schemas import ResearchTask


def test_research_task_accepts_four_cs_specification():
    task = ResearchTask(
        id=1,
        domain="consumer",
        module="Behaviors",
        query="What percentage of U.S. Gen Z coffee drinkers consume cold coffee weekly?",
        rationale="Establish incidence among the target cohort.",
        geography="United States",
        population="Gen Z coffee drinkers",
        time_period="2024-2026",
        evidence_type="quantitative incidence",
        preferred_source_types=["consumer survey", "industry association"],
        freshness="within 3 years",
        minimum_source_quality="high",
        search_queries=["Gen Z cold coffee weekly consumption US survey"],
    )

    assert task.domain == "consumer"
    assert task.module == "Behaviors"
    assert task.minimum_source_quality == "high"
    assert task.preferred_source_types == ["consumer survey", "industry association"]


def test_planner_is_coverage_driven_and_strategy_free():
    prompt = prompts.PLANNER_PROMPT_V2

    assert "CONSUMER" in prompt
    assert "COMPANY" in prompt
    assert "CATEGORY" in prompt
    assert "CULTURE" in prompt
    assert "COVERAGE, NOT A FIXED TASK COUNT" in prompt
    assert "One worker seeks ONE answerable piece of evidence" in prompt
    assert "separate Strategist decides what it means" in prompt


def test_synthesizer_keeps_research_separate_from_strategy():
    prompt = prompts.SYNTHESIZER_PROMPT_V2

    assert "RESEARCH BOUNDARY" in prompt
    assert "Do NOT recommend what a brand should do" in prompt
    assert "Research Gaps" in prompt
    assert "Consumer Findings" in prompt
    assert "Culture Findings" in prompt


def test_fast_depth_is_worker_effort_not_plan_scope():
    human = prompts.planner_human(
        "Research cold brew.",
        "fast",
        [],
        ["consumer", "company", "category", "culture"],
    )
    assert "worker effort only" in human
    assert "do not reduce research-plan coverage" in human
    assert "Required Four Cs domains: consumer, company, category, culture" in human


def test_explicit_four_cs_plan_requires_breadth():
    from research_engine.graph import _planner_coverage_issues

    required = ["consumer", "company", "category", "culture"]
    thin = [
        {"domain": "consumer", "module": "Behaviors", "query": "q1"},
        {"domain": "consumer", "module": "Motivations", "query": "q2"},
        {"domain": "consumer", "module": "Occasions", "query": "q3"},
        {"domain": "consumer", "module": "Perceptions", "query": "q4"},
    ]
    issues = _planner_coverage_issues(required, thin)
    assert any("missing required domains" in issue for issue in issues)
    assert any("at least 12 atomic tasks" in issue for issue in issues)


def test_explicit_four_cs_plan_passes_with_domain_and_module_coverage():
    from research_engine.graph import _planner_coverage_issues

    required = ["consumer", "company", "category", "culture"]
    tasks = []
    modules = {
        "consumer": ["Behaviors", "Motivations", "Occasions"],
        "company": ["Product", "Brand", "Channels"],
        "category": ["Growth", "Competitors", "Pricing"],
        "culture": ["Rituals", "Emerging Signals", "Language"],
    }
    for domain, names in modules.items():
        for module in names:
            tasks.append({"domain": domain, "module": module, "query": f"{domain} {module}"})

    assert _planner_coverage_issues(required, tasks) == []


def test_unselected_domains_are_not_forced():
    from research_engine.graph import _planner_coverage_issues

    tasks = [
        {"domain": "consumer", "module": "Behaviors", "query": "q1"},
        {"domain": "consumer", "module": "Motivations", "query": "q2"},
    ]
    assert _planner_coverage_issues(["consumer"], tasks) == []
