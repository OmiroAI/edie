# Finishing-editor adapters

Decision: keep the finishing application and interchange format configurable.
Status: design for review. No exporter/importer is implemented or certified yet.
OTIO remains the canonical internal timeline; a chosen editor is an output boundary.

## Export profile

A private profile specifies profile_id/version, adapter_id/version, export format,
optional target editor/version, supported feature subset, media-link/packaging mode,
subtitle languages/format, preview settings and unsupported-feature policy.
Candidates may include FCP7 XML, OTIO, AAF or other interchange formats. Listing a
candidate is not a promise of working support. Each adapter must be verified against
its selected feature subset and target application before being marked compatible.

FCP7 XML + per-language SRT + linked media/assets + MP4 remains the first planned
profile. Other profiles preserve a reference preview, dependency manifest and loss
report while choosing suitable editable timeline/subtitle formats. No editor/version
is fixed globally, and the broker supplies the desired profile per handoff request.

## Adapter interface

- `capabilities(profile)` reports supported import/export features and evidence of
  tested editor versions. Unknown versions are explicitly unverified.
- `preflight(revision, profile)` reports missing assets, unsupported features and
  proposed conversions without mutating the source revision.
- `export(revision, profile, staging_root)` writes a complete package and hashes.
- `validate(package, profile)` checks structural validity, timing and dependencies.
- `import_return(package, base_revision, profile)` produces a new candidate OTIO
  revision, mappings, preserved original payload and compatibility/conflict report.

Do not equate import capability with export capability or assume either preserves
all effects. Preserve unknown features as evidence and block required fidelity.
A rendered substitute needs explicit operator acceptance of lost editability.
The final package records what remained editable and what was baked.

## Compatibility matrix and acceptance

Track each `(adapter version, format version, editor version, feature)` as untested,
passed, lossy or unsupported. Test cuts, frame rates, audio sync/channels, gaps,
tracks, subtitles, markers, media relinking and then each extra effect independently.
An adapter library round trip is a unit/integration test. Human import/edit/export
in the real finishing application is the compatibility acceptance test.

The broker transports packages/returns through the shared-directory contract and
records which editor/version produced a return. If only an accepted MP4 master is
returned, preserve that as authoritative regardless of the original export profile.
