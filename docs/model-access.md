# Model access design

Implementation update: [runtime workflow](runtime-workflow.md) records the current
implemented subset, commands, validation and remaining limits. The detailed target
contracts below extend beyond that subset.

Status: adapter design grounded in the operator's existing CLI and local inference
setup. The runtime adapters, credential isolation and routing enforcement are not
implemented. Deployment addresses, model aliases and private provenance belong in
operator configuration, outside this repository.

## Selected adapter boundaries

| Capability | Adapter | Inputs | Output |
| --- | --- | --- | --- |
| Agent decisions, scripts and revision planning | Codex CLI exec | Bounded text context and tool observations; images only if separately permitted | Structured decision, tool events, final result and usage |
| Visual observation and rendered-preview review | OpenAI-compatible chat completions to configured local VLM | Ordered sampled frames with source timestamps and bounded prompt | Grounded observations, uncertainty and evidence references |
| Speech transcription | Whisper-compatible audio transcriptions API | Locally extracted audio chunk, language hint when known | Verbatim transcript with segment timestamps and uncertainty |

Local visual and speech models are separate tools used by the Codex-driven agent.
Changing the visual route does not change the reasoning runtime. Raw footage does
not need to enter the Codex context. However transcripts and visual descriptions
are also private payloads: subscription usage is not permission to send them to a
cloud service. Route policy must explicitly allow the actual text/images supplied.

## Codex adapter contract

Use the installed CLI as the initial integration, rather than reimplementing its
provider protocol. The inspected CLI supports `exec`, model selection, JSONL events,
stdin prompts, `--output-schema`, `--output-last-message`, ephemeral execution and
ignoring ambient user config. Pin and test the version inside the worker image;
host availability does not mean the current Edie image includes Codex (it does not).

Construct arguments as an array. Supply a task-specific model through deployment
configuration, a strict decision schema, a task-local working directory and the
prompt on stdin. Do not inherit the operator's hooks, broad provider configuration
or shell environment. Full shell/tool access is permitted only inside the disposable
sandbox; any CLI sandbox bypass requires the container boundary and network policy
to be established first. No worker may mount the management state or host secrets.

Parse a bounded event stream, correlate invocation/tool results and validate the
final structured decision. Record CLI version, configured/resolved model when
reported, measured usage and unknown fields explicitly. Provider events must not
be treated as authoritative job approval or as guaranteed stable across versions.
Persist Edie checkpoints so restart does not depend on provider session retention.

Use an operator-managed subscription login dedicated to this deployment. Do not
copy another agent's auth files. Token renewal uses the provider's supported login
lifecycle, serialised by a trusted credential owner. Expiry, reuse or rejected-auth
errors park the task for credential recovery; they never switch to an API key or
another paid provider. A credential broker/injection path that keeps renewal
secrets outside arbitrary worker shell access is a prerequisite, not an implemented
feature. Do not claim this isolation merely because a container is disposable.

## Local visual and speech adapters

Use configurable base URLs, model IDs and credential references. The vision adapter
posts bounded multimodal chat requests, validates schema and source evidence, and
preserves the returned model identity for auditing. Start with ordered images;
activate native video only after timestamp and server-limit tests. Advertised
context length is not a safe media budget: enforce frame, pixel and response limits.

The transcription adapter posts multipart audio to `/audio/transcriptions` relative
to the configured `/v1` base. Negotiate a response format that actually supplies
segment times; do not invent timings if the server returns only text. Preserve
chunk offset and stream-origin mapping when converting local times to source time.
Store the original transcript separately from subtitle corrections.

Gateway routing must retain the requested capability. A reachable gateway can
silently fall back to a different model; disable such fallback for visual tasks
or verify an explicit capability-equivalent route. Do not assume a container port
is exposed on its host, or that a successful loopback request proves access from
an isolated Edie container. Do not disable TLS verification to bypass a failed probe.

## Configuration and activation

Each route declares adapter, model, base URL where applicable, credential reference,
billing class, allowed payload classes, input/output limits, timeout, concurrency,
retry policy and fallback policy (default none). Secret values come from private
runtime configuration and never enter prompts, tool results or source control.
Management API authentication remains separate from model authentication.

The operator's private profile records observed endpoints and unresolved checks.
Before activating a route:

1. Verify connectivity and certificate validation from the actual adapter container.
2. Verify authenticated routing/model identity using the deployment's scoped access.
3. Test synthetic text/image/audio payloads, schema handling and timestamp semantics.
4. Confirm downstream fallback policy and permitted outbound payloads.
5. Exercise expired authentication, throttling, cancellation and ambiguous completion
   without unapproved fallback or duplicate side effects.
6. Account for usage and reserve bounded paid costs before any metered request.

Model-list and health checks establish availability only, not generation quality,
authenticated gateway correctness or media compatibility. No route is currently
activated in Edie; existing render/preprocessing workers remain network-isolated.
