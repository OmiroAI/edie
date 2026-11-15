# Editing handoff and broker-mediated human feedback

Status: agreed initial handoff; proposed event/file protocol. Export/import and
human-approval gates remain to be implemented and verified in the finishing app.

## Initial package

Every handoff consists of Premiere-compatible Final Cut Pro 7 XML (`.xml`), one
SRT per subtitle language, linked source media and required assets, and an MP4
reference preview. Include a manifest tying files/hashes to the job, exact revision,
source versions and validation results. Assets must be available through the shared
directory or explicitly included in the package; remote storage credentials are not
part of it. Report effects/styling that cannot be represented faithfully.

Use the FCP7/xmeml interchange family, not a file named XML with an arbitrary schema.
Adobe documents that modern Final Cut Pro X `.fcpxml` requires conversion for
Premiere import. [Adobe import guidance](https://helpx.adobe.com/premiere/desktop/organize-media/import-files/migrate-from-final-cut-pro-x.html).
The [Apple legacy XML reference](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/FinalCutPro_XML/Elements/Elements.html)
provides the interchange vocabulary. Neither document proves our output works in
the chosen finishing-app version: import, modify and return a real package there.

The interchange package is an output contract. [OpenTimelineIO is the chosen
internal timeline representation](timeline.md), with separate subtitle/provenance
records. Its integration and the exporter remain to be implemented and tested.

## Shared-directory ownership

The broker uploads/downloads source copies, previews and returned human edits and
passes human feedback to Edie through authenticated management commands. Suggested
layout: broker-owned `inbox/`, Edie-owned `outbox/`, and Edie's private working state.
Mount inbox read-only for workers; publish outbox packages only after completion.
The broker writes to staging then atomically publishes a ready manifest on the same
filesystem. Edie verifies all listed lengths/hashes before consuming the package.
Do not treat a filename's appearance or a partial upload as readiness or approval.

A proposed broker event contains event ID, job ID, base revision/artifact hash,
event type, human provenance, payload manifest hash and (for feedback) timestamp
basis/range. Deduplicate by event ID and reject reuse with a different payload.
Keep original human text and any broker-normalised instruction together. Free text
such as “looks good” becomes an explicit approval event only after the broker has
resolved its scope with the human; the agent never infers final approval from it.

## Review cycle

1. Edie publishes a revision-bound preview/package and a review request.
2. Broker transfers it and collects timestamped feedback or a returned edit/master.
3. Broker submits the event plus immutable shared-directory payload references.
4. Edie acknowledges receipt, validates the base and preserves the feedback.
5. Edie creates a new revision and returns a concise change/remaining-issues report.
6. Broker conveys explicit script/main/final approval for the exact candidate.

Comments on stale revisions are not silently retimed. Explain differences and ask
for clarification if mapping is ambiguous. Duplicate/reordered events cannot advance
approval or apply the same revision twice. A cancelled job retains incoming feedback
without restarting until explicitly resumed. Contradictory human instructions park
only dependent work while preserving unrelated validated artifacts.

An editable human return becomes a new authoritative revision after compatibility
validation. An accepted finished master becomes the main source of truth for eligible
cutdowns. If editable layers are required and absent, request them through the broker;
never overwrite human work by reverting to the earlier generated timeline.

The broker is the trusted human-provenance boundary. A bearer token authenticates the
broker service, not a human's identity by itself. Record the claimed human actor and
interaction reference; the deployment decides which broker assertions may authorise
approval. No extra Edie messaging bot or parallel approval store is required initially.
