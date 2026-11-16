"""Text-only subscription decision adapter. No provider credential copying."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


class Codex:
    def __init__(self, model, allowed_payloads, timeout=240):
        if 'private_text' not in allowed_payloads:
            raise ValueError('Private text export to Codex is not authorised')
        self.model=model;self.timeout=timeout

    def decide(self, prompt, schema):
        if len(prompt.encode())>256*1024:raise ValueError('Decision context too large')
        # The trusted operator process owns login. Child receives no API keys,
        # media mounts, management token or arbitrary worker shell capability.
        with tempfile.TemporaryDirectory(prefix='edie-decision-') as directory:
            root=Path(directory);spec=root/'schema.json';output=root/'answer.json'
            spec.write_text(json.dumps(schema))
            args=['codex','exec','--ignore-user-config','--ignore-rules','--ephemeral',
                  '--skip-git-repo-check','--sandbox','read-only','--model',self.model,
                  '--disable','shell_tool','--disable','apps','--disable','multi_agent',
                  '--disable','multi_agent_v2','--disable','view_image','--disable','image_generation',
                  '--disable','browser_use','--disable','computer_use','--disable','unified_exec',
                  '--enable','skip_host_skill_discovery','-c','project_doc_max_bytes=0',
                  '-c','web_search="disabled"','-c','model_reasoning_effort="medium"',
                  '-C',directory,'--output-schema',str(spec),'--output-last-message',str(output),
                  '--json','-']
            environment={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','CODEX_HOME')}
            start=time.monotonic()
            with tempfile.TemporaryFile() as events:
                result=subprocess.run(args,input=('Return only the requested structured decision. Edie mediates every tool; do not invoke CLI tools or read files.\n'+prompt).encode(),stdout=events,stderr=subprocess.DEVNULL,env=environment,timeout=self.timeout)
                if result.returncode or not output.is_file():raise ValueError('Codex decision failed; check subscription login/availability')
                if output.stat().st_size>1024*1024:raise ValueError('Decision response too large')
                usage=None
                events.seek(0)
                for line in events:
                    if len(line)>2*1024*1024:continue
                    try:event=json.loads(line)
                    except ValueError:continue
                    if event.get('type')=='turn.completed':usage=event.get('usage')
                return json.loads(output.read_text()),{'model':self.model,'billing':'subscription','usage':usage,'known_cost_micro_usd':0,'subscription_allocation_cost':'unknown','seconds':time.monotonic()-start}

class CodexSocket:
    """Decision-only local broker. The container receives a socket, never auth."""
    def __init__(self,path,stage='planning'):self.path=path;self.stage=stage
    def decide(self,prompt,schema):
        import socket
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.settimeout(300);connection.connect(self.path)
            stream=connection.makefile('rwb')
            stream.write(json.dumps({'prompt':prompt,'schema':schema,'stage':self.stage}).encode()+b'\n');stream.flush()
            raw=stream.readline(2*1024*1024+1)
            if len(raw)>2*1024*1024:raise ValueError('Broker response too large')
            result=json.loads(raw)
            if 'error' in result:raise ValueError(result['error'])
            return result['decision'],result['usage']


def serve(path,model,models=None):
    import socketserver
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(300)
            try:
                raw=self.rfile.readline(300*1024+1)
                if len(raw)>300*1024:raise ValueError('Broker request too large')
                request=json.loads(raw)
                stage=request.get('stage','planning')
                if stage not in ('planning','review','repair'):raise ValueError('Unknown decision stage')
                selected=(models or {}).get(stage,model)
                decision,usage=Codex(selected,['private_text']).decide(request['prompt'],request['schema'])
                result={'decision':decision,'usage':usage}
            except Exception:result={'error':'Subscription decision unavailable; no fallback attempted'}
            self.wfile.write(json.dumps(result).encode()+b'\n')
    if Path(path).exists():raise ValueError('Broker socket exists; check running owner before removing it')
    with socketserver.UnixStreamServer(path,Handler) as server:
        os.chmod(path,0o600)
        try:server.serve_forever()
        finally:Path(path).unlink(missing_ok=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--socket',required=True);p.add_argument('--model',required=True);p.add_argument('--models-json')
    a=p.parse_args();serve(a.socket,a.model,json.loads(Path(a.models_json).read_text()) if a.models_json else None)
