# V3.1 evidence judgment integration audit

## What could be traced

The September 24 Chameleon report was supplied as finished Markdown, not as the
persisted run's task, evidence, and revision objects. Its cited Commonwealth Joe
paragraph and two market-size estimates can be inspected, but their original task
specifications, attested quotations, attestation grades, and runtime commit cannot be
reconstructed from Markdown. At audit time V3 was an **open, unmerged draft PR #1**;
there is no basis to attribute this particular report to that PR's runtime. The
examples below use representative attested quotations to exercise the actual V3
functions; they are reproducible behavior, not claims about that live run's hidden
state. The report itself cites Commonwealth Joe at [5] and the two market reports
at [21]/[22] and [27].

## V3 before this correction: A–G

| Question | Observed implementation |
| --- | --- |
| A. Structured layer | `findings.SourceAssessment` and `findings.Finding` are Pydantic models; `build_findings` creates dicts. Revision JSON (`Revision.findings`, migration 0027), run detail, and native bundle preserve them for new, nondemo run revisions. Older revisions have `null`. |
| B. Synthesis input | `graph.synthesizer_node` builds findings from `_citable_evidence`, filters real runs to attested quotations, excludes `research_gap` quotations from numbered sources, and feeds `finding` text, status, role and caveats to the model. `finding` itself is the first verbatim source snippet, not a consolidated proposition. The citation fidelity checker later uses all eligible snippets indexed by URL. |
| C. Confidence | A company product fact from one recognized primary-company host can be high. Otherwise high needs two distinct strong publishers and stated task geography/population. One strong publisher gives medium; the remainder are low. Exact repeated wording does not increase independent publisher count; unknown methodology and scope remain caveats. |
| D. Enforcement | Citation fidelity checks whether the cited URL's snippets back wording. After that `_apply_finding_confidence` used **every finding on each cited URL**, regardless of which snippet backed the sentence. It removed unsupported citation indices and prefixed low/medium sentences with mechanical labels. Those labels were added after the citation pass. |
| E. Roles | `_role` derives one role from the task domain/evidence type. The prompt asks the model to respect it, but URL-level matching could transfer the role of a different snippet. `source_class` recognizes a brand host as primary only in a company task. |
| F. Corroboration | `build_findings` groups within a task by identical attested key fact or identical snippet; it counts distinct strong publisher hosts unless text is verbatim identical. It cannot recognize differently worded derivative reports. It does not join cross-task estimates. |
| G. Break | The alignment from a cited **claim** to a particular assessed **quotation** was missing. A source citation established provenance, then URL-level lookup treated all findings from that URL as candidates. Market-size scope lived mostly in task metadata and was not carried into findings or explicitly compared. |

The same `research_engine.graph` synthesizer is called by both hosts for native runs;
server `run_execution.persist_outcome` and desktop sidecar's shared call store the
same revision findings. The older `/research` session journey is a separate path
and does not promise a V3 findings package. Run detail exposes JSON findings,
but the Markdown report renderer displays only authored prose and citations.

## Commonwealth Joe reproduction

Take a Consumer/Motivations task asking why Gen Z in the U.S. chooses cold brew,
and a **hypothetically FETCHED_BODY-attested** snippet at
`commonwealthjoe.com/blogs/blog/sip-snap-share-gen-z-and-cold-brew-culture`
asserting that Gen Z chooses it for smooth taste and healthy habits. The executor's
chunk has `task_id`, `source_url`, `snippet`, and `attestation_grade`; attestation
would require the exact quotation to occur in retrieved tool output. V3's
`assess_source` returns `commercial_blog`, `unsuitable` for the Consumer task,
`consumer_perception` as task role, unknown geographic/population/method fit.
`build_findings` gives it zero independent strong publishers, `low` confidence,
`research_gap`, and suitability/corroboration/scope caveats. The real synthesizer
excludes that quotation from citable sources. If a separate Culture task quotes
the page as an observed expression, it can instead produce an `emerging_signal`;
that permits describing the expression, not attributing a population motivation.
We do not know which tasks or quotations the supplied live run actually used.

## Market-size reproduction

Take one 2024 U.S. cold-brew category-size task with an attested USD 244.69
million quotation and a separate 2025 RTD cold-brew category-size task with an
attested US$ 1.56 billion quotation. V3 creates separate low-confidence findings:
the sources are unrecognized market publisher hosts, their methodology is
unverified, and the literal key facts/task IDs differ. No independent corroboration
is counted, because corroboration occurs only within a finding group. The
contradiction detector checks at most twelve sources and requires the same subject,
scope, period and unit; a different scope/year should not be marked a contradiction.
It did not reconcile apparently incompatible estimates in the findings layer.

## Correction and limits

V3.1 aligns each final cited sentence against the quotations of its cited,
non-gap findings using the existing critic verifier. If no quotation supports it,
or the verifier does not return a usable ruling, the sentence is removed. A
sentence combining independently cited facts is checked against their quotations
together and inherits the most cautious judgment. Qualified and emerging claims
receive cautious language; uncited factual sentences are removed if repair did
not supply a citation. Task scope and unresolved market-size comparisons are
preserved in finding JSON and briefly surfaced in prose. Alignment adds batched
critic calls proportional to the cited claim/quotation candidates, with an
additional call when a combined claim needs several quotations. Its cost and
tokens are included in run accounting. It
does not prove that a quoted publisher's method, market definition or audience
sample is valid. Live behavior still requires a run on this branch with the exact
four-domain Fast/Plan Review configuration and access to its persisted evidence.

## Follow-up: September 24 live acceptance report

The later four-domain Chameleon report contains 32 sources. It cites a coffee
seller's blog for a Gen Z demographic superlative, `glassandnote.com` for several
high-precision pricing figures, `accio.com` for a 59% consumer statistic, and
Commonwealth Joe for aesthetic/cultural observations. It retains competing market
estimates and identifies research gaps. The report file does **not** contain the
run ID, original task JSON, attested snippets, finding JSON, or worker commit.
The prose contains none of the real-mode V3.1 qualification prefixes, so it
cannot independently prove that this branch's final judgment pass executed.

The table below exercises the branch against representative `FETCHED_BODY` excerpts
from those report sources. Its statuses are reproducible code outputs, **not**
retrospective assertions about missing live checkpoint data.

| Diagnostic | Classification → role → finding | Enforced result |
| --- | --- | --- |
| Pure Earth Coffee Gen Z demographic superlative | `commercial_blog`; observed Consumer behavior or, for a quantified Culture superlative, `measured_fact`; unsuitable, Low, gap. The source page's visible statement says fastest-growing; the report adds largest. | No measured population claim from the blog. Literal superlatives must appear in the attested quotation. |
| Commonwealth Joe Instagram aesthetics | `commercial_blog`; cultural occurrence → `cultural_signal`, Low, emerging. | Content depicting visually styled cold brew can remain a signal. The same occurrence cannot ground a bare population generalization about Gen Z behavior. |
| Glass & Note elasticity | `unknown`; pricing quotation containing elasticity → `measured_fact`, limited, Low; method unverified. The original raw statistic is retained in `source_quotes`. | A cited number may be reported with explicit publisher and missing-method attribution; the bare number is not an established measurement. The page was not accessible for independent methodology verification here. |
| Accio 59% sustainability claim | `commercial_vendor`; population percentage → `measured_fact`; unsuitable, Low, gap. The Accio page cites two vendor pages for the statistic, but its quotation does not establish a sample/method. | No consumer prevalence finding from that page alone. Other qualitative sustainability content may still be treated as a limited trend observation. |

The first promotion point was `build_findings`: `finding` had been an exact raw
quotation even for Low/conflicted evidence. The second was final alignment:
`_verifier_verdicts` asked whether text matched a citation, not whether the matched
role, scope or method entitled the report to make that claim. A bare quantitative
claim could thus pass the semantic check and receive only a generic hedge; a
Culture-tagged population assertion could pass as an emerging signal. A third,
unproven risk is a run resumed or published without the current judgment pass;
the real-mode finalizer now refuses such a draft. The report alone cannot
identify whether runtime version mismatch occurred in that specific live run.

No migration is required for `source_quotes` or the checkpoint judgment flag:
findings are stored in an existing JSON revision column and graph state is
JSON-serializable. Old bundles remain readable; the report needs a fresh run to
test the corrected wording and source mix in vivo.
