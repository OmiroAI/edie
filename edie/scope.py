"""Shared library ownership for independently reviewed story outputs."""
import json


def library_job(store,job):
    row=store.db.execute("SELECT body FROM records WHERE kind='job' AND id=?",(job,)).fetchone()
    return json.loads(row[0]).get('output_of',job) if row else job
