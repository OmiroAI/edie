"""Operator-owned private context; immutable versions and an atomic active pointer."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

MAX_BYTES = 1024 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def read_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Context must be an ordinary JSON file below 1 MiB')
    return json.loads(path.read_bytes())


def validate(document):
    if not isinstance(document, dict) or document.get('schema_version') != 1:
        raise ValueError('Context schema_version must be 1')
    for key in ('strategy_id', 'version'):
        if not isinstance(document.get(key), str) or not document[key].strip():
            raise ValueError('Context identity and version required')
    rules = document.get('rules')
    if not isinstance(rules, list) or not rules:
        raise ValueError('Context rules required')
    ids = set()
    for name in ('soul', 'memory'):
        if name in document and not isinstance(document[name], str):
            raise ValueError('Soul and memory must be Markdown text')
    for rule in rules:
        if not isinstance(rule, dict) or not all(isinstance(rule.get(k), str) and rule[k].strip() for k in ('id', 'rule', 'kind')):
            raise ValueError('Each rule needs id, rule and kind')
        if rule['id'] in ids:
            raise ValueError('Duplicate rule ID')
        ids.add(rule['id'])
    payload = canonical(document)
    if len(payload) > MAX_BYTES:
        raise ValueError('Context too large')
    return payload


class Context:
    def __init__(self, directory):
        self.root = Path(directory).expanduser().resolve()

    def _path(self, value):
        if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
            raise ValueError('Invalid context hash')
        return self.root / 'context' / 'versions' / (value + '.json')

    def load(self, value):
        document = read_json(self._path(value))
        if hashlib.sha256(validate(document)).hexdigest() != value:
            raise ValueError('Context integrity failure')
        return document

    def active(self):
        pointer = read_json(self.root / 'context' / 'active.json')
        value = pointer.get('hash')
        document = self.load(value)
        return {'hash': value, 'strategy_id': document['strategy_id'], 'version': document['version']}

    @contextmanager
    def _lock(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory = self.root / 'context'
        directory.mkdir(mode=0o700, exist_ok=True)
        with (directory / '.lock').open('a') as lock:
            os.chmod(lock.name, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def _write(self, path, payload):
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.context-')
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def install(self, document):
        payload = validate(document)
        value = hashlib.sha256(payload).hexdigest()
        with self._lock():
            directory = self.root / 'context' / 'versions'
            directory.mkdir(mode=0o700, exist_ok=True)
            path = self._path(value)
            if path.exists():
                self.load(value)
            else:
                self._write(path, payload)
        return value

    def snapshot(self, version):
        """Capture operator-edited Markdown without changing the active version."""
        document = self.load(self.active()['hash'])
        for name in ('SOUL', 'MEMORY'):
            path = self.root / 'context' / (name + '.md')
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
                raise ValueError('Soul and memory must be ordinary files below 1 MiB')
            document[name.lower()] = path.read_text(encoding='utf-8')
        document['version'] = version
        return self.install(document)

    def activate(self, value, expected):
        # Operator-only action; API/worker mounts are read-only.
        with self._lock():
            self.load(value)
            pointer = self.root / 'context' / 'active.json'
            current = self.active()['hash'] if pointer.exists() else None
            if current != expected:
                raise ValueError('Active context changed; reload before activating')
            self._write(pointer, canonical({'hash': value}))
        return self.active()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config-dir', default=os.getenv('EDIE_CONFIG_DIR'))
    sub = parser.add_subparsers(dest='command', required=True)
    install = sub.add_parser('install')
    install.add_argument('file')
    activate = sub.add_parser('activate')
    activate.add_argument('hash')
    activate.add_argument('--expected', required=True, help='Current hash, or none for initial activation')
    sub.add_parser('status')
    snapshot = sub.add_parser('snapshot')
    snapshot.add_argument('--version', required=True)
    args = parser.parse_args()
    if not args.config_dir:
        parser.error('--config-dir or EDIE_CONFIG_DIR required')
    context = Context(args.config_dir)
    if args.command == 'install':
        print(json.dumps({'hash': context.install(read_json(Path(args.file)))}))
    elif args.command == 'activate':
        print(json.dumps(context.activate(args.hash, None if args.expected == 'none' else args.expected)))
    elif args.command == 'snapshot':
        print(json.dumps({'hash': context.snapshot(args.version)}))
    else:
        print(json.dumps(context.active()))


if __name__ == '__main__':
    main()
