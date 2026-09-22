from research_engine import claims, graph as graph_mod


def test_uncited_splitter_does_not_break_us_abbreviation():
    draft = (
        "# Title\n\n"
        "## Findings\n"
        "Younger U.S. consumers are adopting cold brew quickly [1]. "
        "Convenience matters to younger consumers.\n"
    )

    uncited = []
    for raw in draft.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        content = graph_mod._VLIST_MARKER_RE.sub("", line)
        for sentence in claims.split_sentences(content):
            s = sentence.strip()
            if not claims.is_claim_sentence(s):
                continue
            if not claims.CITE_RE.search(s):
                uncited.append(s)

    assert uncited == ["Convenience matters to younger consumers."]
