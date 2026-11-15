# Working on Edie

Edie is a generic, self-hostable video-editor assistant built on Codex. Build a
new application; supplied skills and other projects are references, not code to
port wholesale. Read README.md and relevant docs before making changes.

- Document system architecture, API contracts, data models, processing pipelines
  and significant design decisions in `docs/`. Update those documents alongside
  implementation changes, link them from README.md, and distinguish proposed,
  implemented and verified behaviour. Include recovery and validation where relevant.
- Keep reusable code generic. Footage, project prompts, branding, learned context,
  source manifests and deployment-specific configuration stay private and outside
  this public repository. Never commit secrets, private fleet records or raw logs.
  Supply secrets at runtime through private, ignored `.env` files; keep them out
  of images, logs and model prompts.
- Edie consumes explicitly mounted local media. An external broker owns storage
  credentials, authoritative source mappings and remote changes. Edie returns
  structured proposals; it must not rename or delete remote originals itself.
- Use configurable task-specific model routes. Keep visual analysis separate from
  transcription. Prefer local/subscription usage; no automatic paid fallback,
  unapproved uploads or automatic publishing. Enforce configured job budgets.
- Workers may use tools and shell inside their configured sandbox, without host
  deployment privileges. Never mount the Docker socket or host credentials into
  editing workers.
- Preserve source references, original transcripts and human edits. Bind feedback
  and approvals to the correct job/revision. Approve the main edit before creating
  derivatives; use an accepted returned master rather than an obsolete rough cut.
  Learn only from accepted feedback into visible, reversible project-local context.
- Preserve existing edits and runtime data. Work on feature branches and run
  checks appropriate to the change. Do not claim completion from mocks or a
  dashboard: acceptance requires real authorised footage, actual finishing-app
  handoff, export validation and demonstrated recovery.
