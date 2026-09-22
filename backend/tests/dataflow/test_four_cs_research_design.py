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
