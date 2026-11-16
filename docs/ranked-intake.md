# Edie-first intake and ranked review

Implemented: the coordinator reconciles source availability from existing semantic
segment analysis before agent turns, including when no story run is requested. This
adds no model calls or media uploads. It waits for dense indexing and semantic segments;
partial evidence is labelled **Edie analysing**, not an editorial rejection.

## Ranking and decisions

The file's rank is the maximum intrinsic usefulness score among its non-rejected,
profile-2 semantic segments. It is not a confidence probability, an average across dead
time or the story-fit score. One useful moment can justify keeping a whole file.
The initial policy threshold is 70, configurable through the coordinator's runtime
`EDIE_INTAKE_REVIEW_THRESHOLD` integer (0–100). Scores below the threshold require review.

Edie keeps a densely indexed file when at least one semantic segment meets the threshold
and has no `needs_review` label. Otherwise it asks for judgement. Uncertain evidence can
require review even above the threshold. Low usefulness, low brief fit, lack of dialogue,
or Blooper alone never cause automatic exclusion. Mistaken/poor-quality recordings
without sufficient positive evidence are flagged for review, not deleted.

Exact SHA-256 duplicates may be suggested Exclude only when another current source in
the same job is kept. Human-kept representatives take priority. A redundant duplicate
has rank 0 and requires review below a positive threshold. Near duplicates are not
identified by this policy. No local/remote original is deleted or renamed.

Suggestions are revisioned and audited with actor `edie-intake-v1`, source version/hash,
policy profile, evidence hash, score, threshold, status, review requirement and reason.
Human overrides always win, including an explicit return to Unreviewed. Unchanged
suggestions are not rewritten on every coordinator tick. Changed evidence refreshes
suggestions; exact selection confirmation is invalidated when decisions/segments change.
Old whole-file role suggestions are not treated as intake decisions.

## Review interface

Review mode walks the entire job library from lowest rank to highest, with filename as
the deterministic tie-breaker. It clears list filters on entry and snapshots the order
so new analysis cannot move the current file mid-review. **Save & next** persists the
human choice, then advances. It continues through higher-ranked suggestions after the
flagged files; users may leave mode at any time. Pending files remain visible as awaiting
analysis. Re-entering mode rebuilds the order from current ranks.

Cards show rank, availability and review status. The detail panel shows the threshold,
automatic reasoning and editable override. Filters distinguish files needing judgement
from those still being analysed; sorting includes Lowest rank first. Confident decisions
do not require individual clicks. The shared library still requires explicit selection
confirmation before story proposals, and scripts/exports retain their own approval gates.

**Play source** sits inside the player placeholder, centered as a large play control.
Preparation/loading feedback stays there; if a proxy is queued, the control offers a
status check. Once loaded, native video controls handle playback. Transcript timestamps
and visual moment controls continue to seek within the same source player.

## API and verification

`footage` exposes `intake_status` and `review_required`, with ranking/threshold/reason
under `classification.suggestion`. Effective decisions prefer human overrides. Progress
counts separate `human_review` and `pending_intake`; both remain unresolved for selection
confirmation. The existing disposition endpoint remains the sole human override path.

Tests cover automatic keep, conservative uncertainty, pending evidence, exact duplicates,
threshold configuration, idempotence and human authority. Chromium checks low-to-high
review continuation and the in-player source control using synthetic footage. Production
editorial judgement and finishing-app acceptance remain separate from these checks.
