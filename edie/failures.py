"""Allowlisted failure codes: never expose exception text or provider output."""
CODES={
    'Invalid semantic partition':'segment_invalid_partition',
    'Proposed boundary splits speech':'segment_splits_speech',
    'Incomplete semantic partition':'segment_incomplete_partition',
    'Empty segment proposal':'segment_empty_proposal',
    'Segment context exceeds budget; refine brief or source scope':'segment_context_limit',
    'Queued segment source changed':'segment_source_changed',
    'Subscription decision unavailable; no fallback attempted':'subscription_unavailable',
}
SAFE_CODES=set(CODES.values())|{'segment_schema_invalid','segment_timeout','segment_index_failed'}

def segment_failure(error):
    from jsonschema import ValidationError
    if isinstance(error,ValidationError):return 'segment_schema_invalid'
    if isinstance(error,TimeoutError):return 'segment_timeout'
    return CODES.get(str(error),'segment_index_failed')
