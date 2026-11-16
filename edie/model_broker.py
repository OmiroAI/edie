"""Restricted local inference transport for network-isolated containers."""
import argparse
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import socketserver
import threading
import urllib.request
from .models import NoRedirect


def serve(path,routes):
    limits={name:threading.BoundedSemaphore(route.get('concurrency',1)) for name,route in routes.items()}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            self.connection.settimeout(240)
            try:
                route_name={'/chat/completions':'vision','/audio/transcriptions':'speech'}[self.path]
                route=routes[route_name]
                length=int(self.headers.get('Content-Length',0))
                if not 0<length<=16*1024*1024:raise ValueError('Payload limit')
                body=self.rfile.read(length)
                if len(body)!=length:raise ValueError('Incomplete request')
                content_type=self.headers.get('Content-Type','')
                if route_name=='vision':
                    parsed=json.loads(body)
                    if parsed['model']!=route['model']:raise ValueError('Model route mismatch')
                    required={'text','frames'}
                else:
                    from email.parser import BytesParser
                    mime=BytesParser().parsebytes(('Content-Type: '+content_type+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+body)
                    models=[part.get_payload(decode=True).decode() for part in mime.get_payload() if part.get_param('name',header='content-disposition')=='model']
                    if models!=[route['model']]:raise ValueError('Speech model route mismatch')
                    required={'audio'}
                if not required<=set(route['allowed_payloads']) or route['billing']!='local' or route.get('fallback') is not None:raise ValueError('Route not allowed')
                headers={'Content-Type':content_type}
                if route.get('credential_env'):
                    headers['Authorization']='Bearer '+os.environ[route['credential_env']]
                request=urllib.request.Request(route['base_url'].rstrip('/')+self.path,data=body,headers=headers)
                with limits[route_name]:
                    with urllib.request.build_opener(NoRedirect).open(request,timeout=route.get('timeout',180)) as response:
                        result=response.read(2*1024*1024+1)
                if len(result)>2*1024*1024:raise ValueError('Response limit')
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(result)));self.end_headers();self.wfile.write(result)
            except Exception:
                self.send_response(502);self.send_header('Content-Length','0');self.end_headers()
    class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):daemon_threads=True
    if Path(path).exists():raise ValueError('Socket already exists; verify owner before cleanup')
    with Server(path,Handler) as server:
        os.chmod(path,0o600)
        try:server.serve_forever()
        finally:Path(path).unlink(missing_ok=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--socket',required=True);p.add_argument('--routes',required=True);a=p.parse_args()
    serve(a.socket,json.loads(Path(a.routes).read_text()))
