"""Trusted launcher for disposable, offline shell tools; no Docker socket in workers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import subprocess
import tempfile
import time


def execute(image,media,work_root,request):
    identifier=request['invocation']
    if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('Invalid invocation')
    command=request['command'];timeout=request.get('timeout',120)
    if not isinstance(command,str) or len(command.encode())>32768 or not isinstance(timeout,int) or not 1<=timeout<=300:raise ValueError('Invalid command limits')
    root=Path(work_root).resolve();root.mkdir(parents=True,exist_ok=True)
    work=root/identifier
    work.mkdir(mode=0o700)  # No replay into an existing command workspace.
    name='edie-tool-'+identifier
    args=['docker','run','--rm','--pull','never','--name',name,'--network','none','--read-only',
          '--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','128','--memory','2g','--cpus','2',
          '--user',f'{os.getuid()}:{os.getgid()}','--tmpfs','/tmp:rw,size=256m',
          '--mount',f'type=bind,src={Path(media).resolve()},dst=/media,readonly',
          '--mount',f'type=bind,src={work},dst=/work','--workdir','/work','-i','--entrypoint','sh',image,'-s']
    started=time.monotonic();reason=None
    with tempfile.TemporaryFile() as output:
        process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=output,stderr=subprocess.STDOUT)
        try:
            process.stdin.write(command.encode());process.stdin.close()
            while process.poll() is None:
                if time.monotonic()-started>timeout or os.fstat(output.fileno()).st_size>1024*1024:
                    reason='time_or_output_limit';break
                # Workspace quota is checked during execution; symlinks excluded.
                if sum(p.stat().st_size for p in work.rglob('*') if p.is_file() and not p.is_symlink())>512*1024*1024:
                    reason='workspace_limit';break
                time.sleep(.2)
        finally:
            subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        # Never forward arbitrary shell output to a cloud model. This avoids
        # silently sending media encoded into stdout under a text-only policy.
        artifacts=[]
        for path in work.rglob('*'):
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(work):continue
            with path.open('rb') as stream:value=hashlib.file_digest(stream,'sha256').hexdigest()
            artifacts.append(dict(path=str(path.relative_to(work)),bytes=path.stat().st_size,sha256=value))
        return dict(invocation=identifier,exit_code=process.returncode,limit=reason,seconds=time.monotonic()-started,artifacts=artifacts,stdout='not forwarded',authoritative_changes=False)


def request(path,command,invocation,timeout=120):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout+60);connection.connect(path);stream=connection.makefile('rwb')
        stream.write(json.dumps(dict(command=command,invocation=invocation,timeout=timeout)).encode()+b'\n');stream.flush()
        raw=stream.readline(1024*1024)
        result=json.loads(raw)
        if 'error' in result:raise ValueError(result['error'])
        return result


def serve(path,image,media,work):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(360)
            try:
                raw=self.rfile.readline(65537)
                if len(raw)>65536:raise ValueError('Request limit')
                result=execute(image,media,work,json.loads(raw))
            except Exception:result={'error':'Sandbox command failed; reconcile staged workspace before retry'}
            self.wfile.write(json.dumps(result).encode()+b'\n')
    if Path(path).exists():raise ValueError('Socket already exists')
    with socketserver.UnixStreamServer(path,Handler) as server:
        os.chmod(path,0o600)
        try:server.serve_forever()
        finally:Path(path).unlink(missing_ok=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--socket',required=True);p.add_argument('--image',required=True);p.add_argument('--media',required=True);p.add_argument('--work',required=True);a=p.parse_args();serve(a.socket,a.image,a.media,a.work)
