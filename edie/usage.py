"""Usage facts without prompt, response, credential or raw provider logging."""
import fcntl
import json
import os
import time
import uuid
from pathlib import Path


def record(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
    with os.fdopen(fd,'a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        stream.write(json.dumps(dict(id=uuid.uuid4().hex,time=time.time(),**value))+'\n');stream.flush();os.fsync(stream.fileno())


def summary(entries):
    known=0;unknown=0;tokens=0;calls=0
    for entry in entries:
        calls+=1
        cost=entry.get('known_cost_micro_usd')
        if cost is None:unknown+=1
        else:known+=cost
        usage=entry.get('usage') or {}
        tokens+=usage.get('total_tokens',usage.get('input_tokens',0)+usage.get('output_tokens',0))
    return dict(calls=calls,reported_tokens=tokens,known_cost_micro_usd=known,calls_with_unknown_cost=unknown,subscription_allocation_cost='unknown')
