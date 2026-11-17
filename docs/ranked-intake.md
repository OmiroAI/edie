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
regardless of segment uncertainty labels. Otherwise it asks for judgement. Segment
uncertainty remains visible in segment review; a high file rank makes the source
available, not mandatory in a script. Low usefulness, low brief fit, lack of dialogue,
or Blooper alone never cause automatic exclusion. Mistaken/poor-quality recordings
without sufficient positive evidence are flagged for review, not deleted.

Exact SHA-256 duplicates may be suggested Exclude only when another current source in
the same job is kept. Human-kept representatives take priority. A redundant duplicate
has rank 0 and requires review below a positive threshold. Near duplicates are not
identified by this policy. No local/remote original is deleted or renamed.

Suggestions are revisioned and audited with actor `edie-intake-v1`, source version/hash,
policy profile, evidence hash, score, threshold, status, review requirement and reason.
Human overrides always win, including an explicit return to Unreviewed (which still requires a manual decision in the ordinary
library if the rank is above the review-mode threshold). Unchanged
suggestions are not rewritten on every coordinator tick. Changed evidence refreshes
suggestions; exact selection confirmation is invalidated when decisions/segments change.
Old whole-file role suggestions are not treated as intake decisions.

## Review interface

Review mode walks only analysed files below the threshold without a confirmed human
Keep/Exclude decision, from lowest rank to highest, with filename as
the deterministic tie-breaker. It clears list filters on entry and snapshots the order
so new analysis cannot move the current file mid-review. **Save & next** persists the
human choice, then advances. It stops when that queue is complete. Higher-ranked suggestions and pending analysis
remain available in the ordinary library, outside Review mode. Re-entering mode rebuilds the remaining queue from persisted decisions and current ranks.
Confirmed files stay accessible in the ordinary library, but never appear in Review mode.
An explicit Unreviewed decision puts a file back into the queue.

Cards show rank, availability and review status. The detail panel shows the threshold,
Edie’s suggestion and Your decision in separate sections. A Confirm Edie’s suggestion
button persists a human decision against the exact classification revision and stores
the confirmed suggestion snapshot. Choosing a different disposition overrides it; it
does not replace or erase the agent suggestion. Automatic availability is not labelled
as a human confirmation. Filters distinguish files needing judgement
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

## Explicit legacy score migration

`edie.rescale.rescale(store, job)` is an operator-invoked migration, not a runtime
heuristic. For authorised legacy profile-2 agent segments, scores 1–5 are multiplied
by 20 for both intrinsic usefulness and story fit. Existing scores above 5, human-edited
segments, boundaries, labels, selections and file Keep/Exclude decisions are preserved.
Original values and `score_scale=100` are retained on the segment, and the segment
revision/audit event is updated. Repeating the migration does not multiply scores again.
File suggestion ranks are refreshed, while human decisions and their confirmation
snapshots are unchanged. Duplicate priority remains zero. Future semantic prompts give
explicit 0–100 anchors and mark the output scale. New records with that marker are never
rescaled, even when their legitimate score is below 6.

Migration tests verify ordering, idempotence and preserved exclusions. Browser tests
confirm a low-ranked file, exit/re-enter, verify only the remaining file appears, confirm
its suggestion and verify the completed queue does not reopen. Selection confirmation
still uses exact decisions/segments, so changed score records require reconfirmation.

### Threshold-only review and accurate counters

The Review mode button and Review flagged files banner both reload current records and
start the same ascending queue: no human Keep/Exclude, analysis available, score strictly
below the configured threshold (70 by default). Exactly 70 is outside this queue. No
higher-ranked suggestion is added at the end. File progress separates human-confirmed,
automatically suggested, awaiting analysis and requiring-review counts; it never calls
an automatic suggestion a human decision. The ordinary library supports optional
confirmation/override of all scores. Historical task error results are shown as errors
only while the task is failed/interrupted, not while a recovered attempt is running.
