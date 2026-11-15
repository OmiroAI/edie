import argparse
import json
from .core import Store, render


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', default='state')
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('project')
    create.add_argument('name')
    job = commands.add_parser('job')
    job.add_argument('project')
    job.add_argument('brief', type=json.loads)
    revision = commands.add_parser('revision')
    revision.add_argument('job')
    revision.add_argument('clips', type=json.loads)
    preview = commands.add_parser('render')
    preview.add_argument('revision')
    preview.add_argument('--media', required=True)
    args = parser.parse_args()
    store = Store(args.state)
    if args.command == 'project':
        print(store.project(args.name))
    elif args.command == 'job':
        print(store.job(args.project, args.brief))
    elif args.command == 'revision':
        print(store.revision(args.job, args.clips))
    else:
        print(render(store, args.revision, args.media))
