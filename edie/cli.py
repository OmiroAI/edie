import argparse
import json
from .core import Store, render
from .index import Catalogue
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', default='state')
    commands = parser.add_subparsers(dest='command', required=True)
    job = commands.add_parser('job')
    job.add_argument('brief', type=json.loads)
    revision = commands.add_parser('revision')
    revision.add_argument('job')
    revision.add_argument('clips', type=json.loads)
    preview = commands.add_parser('render')
    preview.add_argument('revision')
    preview.add_argument('--media', required=True)
    ingest = commands.add_parser('ingest')
    ingest.add_argument('manifest')
    ingest.add_argument('--media', required=True)
    args = parser.parse_args()
    store = Store(args.state)
    if args.command == 'job':
        print(store.job(args.brief))
    elif args.command == 'revision':
        print(store.revision(args.job, args.clips))
    elif args.command == 'ingest':
        entries = json.loads(Path(args.manifest).read_text())
        print(json.dumps(Catalogue(store).ingest(entries, args.media)))
    else:
        print(render(store, args.revision, args.media))
