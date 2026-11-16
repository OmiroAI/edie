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
    human = commands.add_parser('human-return')
    human.add_argument('job');human.add_argument('base_revision');human.add_argument('--inbox',required=True);human.add_argument('--path',required=True);human.add_argument('--sha256',required=True)
    returned = commands.add_parser('import-timeline')
    returned.add_argument('job');returned.add_argument('base_revision');returned.add_argument('--inbox',required=True);returned.add_argument('--media',required=True);returned.add_argument('--manifest',required=True)
    args = parser.parse_args()
    store = Store(args.state)
    if args.command == 'job':
        print(store.job(args.brief))
    elif args.command == 'revision':
        print(store.revision(args.job, args.clips))
    elif args.command == 'import-timeline':
        from .returns import import_timeline
        print(import_timeline(store,args.job,args.base_revision,args.inbox,json.loads(Path(args.manifest).read_text()),args.media))
    elif args.command == 'human-return':
        from .returns import import_master
        print(import_master(store,args.job,args.base_revision,args.inbox,args.path,args.sha256))
    elif args.command == 'ingest':
        entries = json.loads(Path(args.manifest).read_text())
        print(json.dumps(Catalogue(store).ingest(entries, args.media)))
    else:
        print(render(store, args.revision, args.media))
