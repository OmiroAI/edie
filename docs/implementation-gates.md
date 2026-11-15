# Implementation and acceptance gates

The initial core is not ready for production. Completion requires real authorised
footage, actual finishing-application round trips and interruption recovery.
Unit tests and synthetic clips cannot satisfy those gates.

Still to implement:

- Codex execution in a separate sandbox with task-specific configurable models,
  isolated subscription renewal, structured outputs and no management secrets.
- Separate visual and Whisper-compatible transcription adapters; verified
  deployment endpoints, explicit payload permissions and no paid fallback.
- Broker manifests with stable source IDs, source versions and incremental
  reusable metadata; scoped organisation proposals and collision validation.
- Source-linked story scripts, missing-footage reporting and script approval.
- Layered rendering, graphics, transitions, grammar-preserving timed subtitles,
  uncertain terminology, transcript preservation and subtitle languages.
- Premiere-compatible FCP7 XML, assets, per-language SRT and reference preview;
  editable human-return ingestion and accepted-master precedence.
- Production API hardening and dashboard sharing the same durable records.
  A development bearer-token API now supports records and task submission.
- Revision lifecycle, accepted-edit protection, render deduplication and
  frame-level recovery checkpoints. A render worker now handles leases, running
  pause/cancel requests, explicit recovery and artifact publication.
- Main approval before derivatives, final approval, delivery packages, covers,
  posting materials and reversible project-local accepted-feedback learning.
- Per-video budget reservations, actual model usage/cost/retry accounting.
- Export stream/timing/bounds validation and visual/audio defect review beyond
  the currently implemented decode and duration checks.
- API security, integration, Docker and real-render test suites and CI.

Operator inputs outstanding: authorised footage mount and broker manifest,
finishing application/version, subtitle languages, style baseline, approved
cloud payloads and model routes. Private integrations must remain outside the
public source tree. The management API is also the intended initial external
agent integration; messaging adapters must not bypass revision bindings.

Earlier validation: record persistence across reopen,
cross-job approval rejection, traversal and symlink escape rejection. FFmpeg remains unavailable on the host but is installed in the tested Docker
image. Seven tests pass inside Docker, including synthetic rendering through
the queue, source-change rejection, lease recovery and control acknowledgement.
A two-second preview from authorised footage also rendered successfully in a
network-isolated container; private evidence stays outside this repository.
This is a technical render check, not an accepted story or complete workflow.
No inference endpoint has been probed or used.
