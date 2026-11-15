# Agent contracts v1 — proposed for PR approval

Implementation update: [runtime workflow](runtime-workflow.md) records the current
implemented subset, commands, validation and remaining limits. The detailed target
contracts below extend beyond that subset.

Status: design for review, not an implemented API or schema. Approval of this design
is distinct from approval of any video. The [agent loop](agent-loop.md) explains
behaviour; this document specifies the proposed messages and transition rules.

## Common values and boundaries

IDs are opaque strings allocated by the coordinator. Content hashes are SHA-256.
Every message carries `schema_version: 1`; unknown versions, unknown fields and
invalid discriminated-union members are rejected. Timestamps use UTC; editorial
positions use `{value, rate_num, rate_den}` with integer components, positive rate
and half-open ranges. Currency is integer micro-USD, never floating point.

Only the coordinator persists authoritative mutations. Workers receive immutable
inputs and return staged artifacts. A client never chooses arbitrary filesystem
paths: manifests contain scoped relative paths which are resolved and checked
against the permitted mounts. Model output cannot issue approval events.

## Run snapshot

The coordinator creates a snapshot before each decision containing:

| Field | Meaning |
| --- | --- |
| job_id, run_id, turn_id | Job, resumable run and one decision turn |
| state_version | Monotonic job version for compare-and-swap writes |
| context_hash, strategy_hash | Exact deployment context and approved strategy; strategy may be null pending human input |
| brief_hash, plan_version | Current goal/constraints and plan |
| revision_id, revision_hash | Current editing candidate, null before one exists |
| approved_inputs | Exact script/main/delivery approvals and scope |
| evidence_refs, feedback_refs | Bounded source-linked evidence and unresolved human feedback |
| pending_invocations | Durable tasks already dispatched; do not submit duplicates |
| limits | Remaining turns, time, tool calls, disk reservation and model budget |
| tool_catalogue_version | Available tools, argument schemas and route capabilities |

A missing strategy must remain visible. Generic technical indexing may proceed;
style-dependent decisions ask for strategy or an explicit job-specific direction.
Do not invent the operator's brand/style preferences.

## Decision union

Every decision requires `schema_version`, `job_id`, `run_id`, `turn_id`,
`expected_state_version`, `input_snapshot_hash`, `summary`, `plan` and `action`.
`summary` is a concise decision explanation, not hidden reasoning. `plan` contains
stable step IDs, objective, status and evidence references; it cannot grant powers.
`action` is exactly one of:

| Type | Required action fields |
| --- | --- |
| invoke_tool | name, tool_version, arguments, request_key, expected_outcome |
| await_task | invocation_id |
| ask_human | question_id, question, missing_fields, blocked_step_ids |
| request_review | scope (script/main/final), candidate_refs, validation_refs, unresolved_issues |
| blocked | reason_code, dependency_refs, suggested_next_step |
| finish | delivery_manifest_hash, approval_refs, validation_refs |

Illustrative decision (IDs/hashes abbreviated; not a runnable fixture):

```json
{
  "schema_version": 1,
  "job_id": "job-1", "run_id": "run-1", "turn_id": "turn-4",
  "expected_state_version": 12, "input_snapshot_hash": "sha256…",
  "summary": "Inspect the demonstration before selecting it for the opening.",
  "plan": [{"id": "verify-demo", "objective": "Confirm visible result", "status": "in_progress", "evidence_refs": ["source-7:v2"]}],
  "action": {
    "type": "invoke_tool", "name": "inspect_visuals", "tool_version": 1,
    "arguments": {"source_ref": "source-7:v2", "range": {"start": {"value": 90, "rate_num": 30, "rate_den": 1}, "duration": {"value": 120, "rate_num": 30, "rate_den": 1}}, "sampling_profile": "coarse"},
    "request_key": "verify-demo-source7-v2", "expected_outcome": "Timestamped evidence of the product result, or an explicit gap"
  }
}
```

Admission validates snapshot/version, tool arguments, allowed route/payloads,
resource reservation and stage prerequisites. Stale output returns `state_conflict`
and triggers a fresh snapshot. Structural repair attempts are bounded. No invalid
decision is converted into a guessed action.

## Initial typed tools

All source references include stable ID/version/hash. Revision references include
ID/package hash. Arguments below are the required domain fields in addition to
common invocation identity. Collections are reusable source groups, not projects.

| Tool | Domain inputs | Result |
| --- | --- | --- |
| search_footage | query, optional collection_ref, categories, limit | source-linked segments, evidence and coverage |
| read_transcript | source_ref, range, language | verbatim timed segments, uncertainty |
| inspect_visuals | source_ref or artifact_ref (exactly one), range, sampling_profile | timed observations and inspected frame references |
| propose_script | brief_hash, source_refs, supplied_script_ref or draft sections | staged script, evidence links, missing-footage list |
| edit_timeline | base_revision_ref, operations | staged OTIO package, semantic diff, validation report |
| render_preview | revision_ref, output_profile_ref | queued task then MP4 artifact and checks |
| evaluate_edit | artifact_ref, revision_ref, rubric_hash, evidence_refs | criterion grades, evidence coverage, actionable findings |
| prepare_handoff | revision_ref, export_profile_ref, subtitle_languages | package manifest and compatibility report |
| propose_context_change | final_delivery_ref, accepted_feedback_refs, context_hash, proposed_diff | reversible context proposal, no automatic activation |

`edit_timeline.operations` is an atomic ordered batch. Initial operation variants:
insert_clip(track_id, after_item_id or explicit start, source_ref, source_range),
trim_clip(clip_id, source_range), move_clip(clip_id, destination_track_id, start),
replace_clip(clip_id, source_ref, source_range), add_gap(track_id, start, duration),
and set_subtitle(cue_id, language, range, text, transcript_refs). Each explicitly
selects ripple or overwrite semantics where applicable; ambiguous collisions fail.
Changing source selections never mutates original media or transcripts.

A tool observation requires invocation_id, attempt_id, tool_version, input_hash,
status, artifact_refs, evidence_refs, validation_findings, usage and error (null
on success). Status is succeeded/failed/cancelled/uncertain. Error includes a stable
code, retryable flag and safe detail. Codes include invalid_input, state_conflict,
missing_media, unsupported_feature, auth_required, route_denied, quota_exhausted,
transient_transport and uncertain_completion. Usage distinguishes measured values,
estimates and unknowns. Failure does not refund an already incurred provider cost.

## Idempotency, checkpoints and commit

Uniqueness is `(job_id, tool_name, request_key)` with an immutable input hash.
Same key/input returns the existing invocation; different input is a conflict.
Persist invocation and reservation before execution. Return task IDs for long work
and wake the run on durable events instead of spending model turns on polling.

Use a single decision-writer lease per job with a fencing token. Record staged
artifact hashes, validate them, then atomically commit references and state_version.
If feedback arrives during work, retain the result as a candidate but require a
fresh decision before promoting it against changed authoritative state. A worker
cannot commit after lease loss. Unknown provider completion must be reconciled;
never assume a timed-out request was free or had no effect.

Checkpoint after decision acceptance, dispatch, observation, candidate commit and
human-event ingestion. A checkpoint references the snapshot, plan, invocation
ledger, committed artifacts, resource ledger and event cursor. Resume reconciles
pending invocations before deciding again. Temporary provider conversation IDs may
be recorded but are not required to reconstruct authoritative state.

## Human-event and approval transitions

The broker submits event_id, job_id, expected_state_version, type, actor_provenance,
base_candidate_refs and payload. Event-ID deduplication is independent of optimistic
version checks so an identical replay returns its original acknowledgement. The
broker establishes human provenance; a token alone cannot prove human authorship.

| Event | Preconditions | Effect |
| --- | --- | --- |
| instruction/feedback | Referenced job/revision exists | Persist verbatim input; mark affected plan steps for replanning |
| approve_script | Current script hash; unresolved required script checks cleared | Unlock rough-cut generation for that script |
| approve_main | Current validated main candidate; explicit human scope | Pin main source of truth; unlock derivative jobs |
| approve_final | Exact delivery manifest and all required validations | Permit broker delivery request, not social publishing |
| reject | Exact candidate scope | Record rejection; reopen affected steps; no learning |
| human_return | Complete verified manifest and base mapping | Create human-authored candidate; unresolved compatibility blocks promotion |
| revoke_approval | Existing approval reference | Revoke scope; block affected downstream commits; retain history |
| pause/resume/cancel | Valid lifecycle transition | Stop/park/restart permitted work without deleting accepted artifacts |
| delivery_received | Broker acknowledges approved manifest hash | Complete delivery; allow finish and learning proposals |

Main/script changes invalidate only dependent approvals; unrelated source-index
work can remain valid. An accepted returned master replaces the main source of truth
once approved. A conflicting or stale human event stays recorded for reconciliation;
it cannot silently overwrite current work. Human instructions cannot bypass missing
media or technical validation by being misclassified as an approval.

`finish` requires matching final approval, validated requested outputs and broker
receipt. Waiting for a human or broker is a durable parked state, not a busy loop.

## PR review and implementation tests

Review the tool boundaries, required script/main/final gates, explicit delivery
receipt and ripple/overwrite requirement. Aileen's strategy is pending; this design
specifies its interface, not its content. Finishing editor/format remains configurable.

Before runtime activation, implement versioned JSON Schemas and validators with
fixtures for every decision/event variant, unknown fields, wrong types, stale inputs,
idempotency conflicts, uncertain completion, lease loss and approval invalidation.
Add integration traces for human edits during rendering and restart after dispatch.
These are proposed tests; the existing ten media/API tests do not cover this contract.
