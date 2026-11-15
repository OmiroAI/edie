# Strategy context and editorial evaluation

Implementation update: [runtime workflow](runtime-workflow.md) records the current
implemented subset, commands, validation and remaining limits. The detailed target
contracts below extend beyond that subset.

Status: researched design, not an implemented evaluation service. Sources checked
2026-11-15. The test scenarios and starting rubric below are Edie design proposals,
not published benchmarks or a validated predictor of social performance.

## Research findings

Agent evaluation should check the actual resulting environment/artifacts, not only
the agent's claim of success. Use code, model and human graders for different
questions and repeat trials to measure consistency. This informs our split between
render checks, editorial review and workflow outcomes. [Anthropic, agent evaluations](https://www.anthropic.com/research/demystifying-evals-for-ai-agents).

For subjective judgement, prefer specific pass/fail questions or pairwise comparisons
over an unconstrained quality score. Calibrate against human labels and check order
and verbosity biases. This supports using a rubric with examples, a tie option and
human adjudication. [OpenAI, evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

YouTube's retention report distinguishes introductions, top moments, spikes and dips;
a spike can also indicate confusing content being replayed. Treat these as feedback
for investigation, not an automatic instruction to copy an edit pattern. [YouTube,
audience retention](https://support.google.com/youtube/answer/9314415).

## Versioned strategy supplied as deployment context

The deployment owner will provide the actual editorial strategy. It is pending;
no private brand strategy or acceptance baseline is fabricated by this design.


The operator/broker supplies a private strategy package, initially approved by a
human. Edie may propose changes but cannot activate a different strategy merely to
make an evaluation pass. Pin a version/hash per job; a human-directed refresh starts
an explicit revision cycle. The strategy is distinct from model/system instructions.

Required sections:

- Audience and intent: who watches, prior knowledge, desired takeaway and action.
- Viewer promise: what the hook/title/cover promises and what evidence pays it off.
- Formats: requested platform, aspect ratio, duration range and language. Platform
  constraints are dated configuration, not universal hardcoded assumptions.
- Editorial voice: tone, humour, jargon, claim boundaries, forbidden exaggeration.
- Story patterns: useful structures for demonstrations, unboxing, discovery and
  talking-head footage, with exceptions rather than a mandatory identical template.
- Pacing: intentional pauses, acceptable repetition, B-roll relevance and transitions.
  Avoid a universal “cut every N seconds” rule unrelated to the content.
- Visual/audio/subtitle style: asset references, typography, terminology, emphasis,
  music/dialogue balance, readability and accessibility requirements.
- Annotated examples: accepted/rejected segments with timestamps and explanations;
  distinguish rejection for taste from factual or technical errors.
- Evaluation rubric: rule IDs, hard/soft status, evidence required, applicability,
  human-labelled anchors and provisional review thresholds.

A job can override a strategy preference when explicitly instructed, but not safety,
source-grounding or approval rules. Record the override and its author. Unresolved
contradictions produce a focused question rather than silent preference selection.
No brand-specific baseline is invented by this generic design.

## Evaluation layers

| Layer | What is checked | Method |
| --- | --- | --- |
| Integrity | Media exists; hashes/version links; no invented source references | Code assertions and manifest inspection |
| Export | Format/duration, decode errors, A/V and subtitle bounds/timing | Media tools, known fixtures and timeline assertions |
| Workflow | Correct feedback revision, approval gates, accepted-master precedence, retry/recovery | Mocked events plus state/artifact assertions |
| Grounding | Spoken claims and demonstrations are supported; omissions are declared | Evidence-linked rubric and human-labelled cases |
| Editorial style | Viewer promise, clarity, coherent structure, pacing, brand consistency, ending | Human review; calibrated multimodal/model assistance |
| Audience outcomes | Retention, completion, saves/shares or intended action when available | Broker-imported analytics after authorised publishing elsewhere |

Hard failures cannot be averaged away by an attractive edit. Keep technical validity,
grounding and approval results separate from subjective scores. A judge receiving
only a transcript cannot grade composition, subtitle readability or transition
quality. Every grade states which artifact/time ranges and evidence modalities were
examined; incomplete coverage returns unknown/needs-review rather than pass.

## Initial rubric and labels

Use 0 = violates the criterion, 1 = partly meets it/needs revision, 2 = meets it,
and unknown/not-applicable as separate values. Anchor each score with actual
approved examples before enabling automated editorial acceptance. Proposed axes:

1. Hook and payoff: the opening establishes the intended promise and the edit fulfils it.
2. Source grounding: claims remain supported and qualification is preserved.
3. Narrative clarity: ordering makes the demonstration/story understandable.
4. Pacing and relevance: cuts/B-roll serve comprehension; pauses are intentional.
5. Style consistency: the approved voice, assets and terminology are respected.
6. Readability and listening: subtitles are legible; audio does not obscure meaning.
7. Ending/action: the story resolves and requested calls to action are appropriate.

Do not set an arbitrary combined score as a shipping gate. Initially humans approve
editorial readiness; model scores flag likely issues. Freeze rubric/judge versions,
randomise A/B ordering, allow ties and compare agreement per axis. Inspect judge
false passes and false failures, especially confident unsupported-claim approvals.
Use repeated trials of agent and judge where budget permits; report denominators,
variance, cost and latency, not only the best run. Evaluation usage has its own
explicit budget and the same approved-route/payload constraints as editing.

## Starter evaluation set

Build roughly 12–20 private, human-labelled cases first; this size is a proposed
starting workload, not statistical evidence of general reliability. Split by source
collection so near-duplicate footage does not leak from examples into held-out tests.

| Case | Expected outcome |
| --- | --- |
| Product claim without supporting demo | Qualify/remove claim or ask for footage; no invented evidence |
| Hook promises a result missing from the edit | Revise hook or story before requesting review |
| Unboxing with long pauses | Improve flow while preserving meaningful reactions and sequence |
| Brain dump with multiple stories | Select a coherent story; retain reusable index for other jobs |
| Unknown product name | Flag uncertainty; retain verbatim transcript |
| Human says “keep this pause” | Preserve that decision despite general pacing preferences |
| Feedback targets an old preview | Keep revision binding; request clarification or explicit mapping |
| Returned accepted master only | Use master for eligible derivatives; request layers where needed |
| Portrait crop obscures a demonstration | Detect/flag composition issue; do not pass on metadata alone |
| Cut changes subtitle timing | Recompute timing and check rendered synchronisation |
| Worker dies after render before commit | Reconcile without duplicate delivery or lost accepted work |
| Same failed edit repeated | Stop/replan within limits rather than spend indefinitely |
| XML import drops an effect or missing asset | Produce compatibility warning and fail required fidelity check |
| Strategy update mid-job | Keep pinned version until explicit refresh |

For each case store brief, strategy version, authorised input references/hashes,
expected behaviours, forbidden outcomes, relevant human labels and allowed variance.
Do not require one exact script, cut sequence or tool trajectory if several valid
solutions satisfy the brief. Track regression cases separately from exploratory
capability cases. Promote real accepted/rejected examples only with operator consent;
public CI uses synthetic media and mocks, private footage stays outside Git.

## Performance learning

Offline style conformity does not establish virality. If the broker supplies later
analytics, record platform/date, duration, exposure and audience context. Compare
comparable formats and treat small samples and distribution differences explicitly.
Suggest hypotheses for human-reviewed strategy updates; do not claim causation from
one successful post. Edie does not publish or obtain platform credentials for this.
