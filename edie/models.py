"""Explicit model routes; bounded payloads, no fallback and no secret logging."""
import base64
import json
import math
import os
import time
import urllib.request
import urllib.parse
import uuid
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Model redirects are not permitted')


class Route:
    def __init__(self, config):
        self.config = config
        if config.get('billing') not in ('local', 'subscription'):
            raise ValueError('Metered routes are not enabled')
        if config.get('fallback') is not None:
            raise ValueError('Automatic fallback is forbidden')
        url = config['base_url']
        if not url.startswith(('http://', 'https://')) or urllib.parse.urlsplit(url).username or urllib.parse.urlsplit(url).query or urllib.parse.urlsplit(url).fragment:
            raise ValueError('Invalid model endpoint')
        self.base = url.rstrip('/')

    def request(self, endpoint, body, content_type, payloads):
        start=time.monotonic();usage=None
        try:
            result,usage=self._request(endpoint,body,content_type,payloads)
            return result,usage
        finally:
            usage_file=self.config.get('usage_file') or os.getenv('EDIE_USAGE_FILE')
            if usage_file:
                from .usage import record
                record(usage_file,usage or dict(model=self.config['model'],billing=self.config['billing'],seconds=time.monotonic()-start,known_cost_micro_usd=None,status='failed_or_uncertain'))

    def _request(self, endpoint, body, content_type, payloads):
        if not set(payloads) <= set(self.config['allowed_payloads']):
            raise ValueError('Payload not permitted by route')
        if len(body) > self.config.get('max_request_bytes', 16*1024*1024):
            raise ValueError('Model request too large')
        headers = {'Content-Type': content_type}
        credential = self.config.get('credential_env')
        if credential and not self.config.get('socket'):
            value = os.environ.get(credential)
            if not value:
                raise ValueError('Model authentication required')
            headers['Authorization'] = 'Bearer ' + value
        request = urllib.request.Request(self.base + endpoint, data=body, headers=headers)
        start = time.monotonic()
        if self.config.get('socket'):
            import socket
            import http.client
            class Connection(http.client.HTTPConnection):
                def connect(connection):
                    connection.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
                    connection.sock.settimeout(self.config.get('timeout',180))
                    connection.sock.connect(self.config['socket'])
            connection=Connection('localhost')
            try:
                connection.request('POST',endpoint,body,{'Content-Type':content_type})
                response=connection.getresponse()
                if response.status!=200:raise ValueError('Local model broker failed; no fallback')
                raw=response.read(2*1024*1024+1)
            finally:connection.close()
        else:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=self.config.get('timeout', 180)) as response:
                raw = response.read(2*1024*1024+1)
        if len(raw) > 2*1024*1024:
            raise ValueError('Model response too large')
        result = json.loads(raw)
        return result, {'seconds': time.monotonic()-start, 'model': self.config['model'],
                        'reported_model': result.get('model'), 'usage': result.get('usage'),
                        'billing': self.config['billing'], 'known_cost_micro_usd': 0,
                        'subscription_allocation_cost': 'unknown'}

    def chat(self, prompt, frames=(), schema=None):
        if len(frames)>self.config.get('max_frames',32):raise ValueError('Frame limit exceeded')
        if any(Path(f['path']).stat().st_size>1024*1024 for f in frames):raise ValueError('Frame too large')
        content = [{'type': 'text', 'text': prompt}]
        for frame in frames:
            content.append({'type': 'text', 'text': f"Source time {frame['seconds']:.3f} seconds"})
            content.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,'+base64.b64encode(Path(frame['path']).read_bytes()).decode()}})
        body = {'model': self.config['model'], 'messages': [{'role': 'user', 'content': content}],
                'max_tokens': self.config.get('max_tokens', 2048), 'temperature': 0.2,
                'chat_template_kwargs': {'enable_thinking': False}}
        if schema:
            body['response_format'] = {'type': 'json_schema', 'json_schema': {'name': 'result', 'strict': True, 'schema': schema}}
        result, usage = self.request('/chat/completions', json.dumps(body).encode(), 'application/json', ['text'] + (['frames'] if frames else []))
        if result.get('model') not in self.config.get('accepted_models', [self.config['model']]):
            raise ValueError('Unexpected model identity; possible fallback')
        return result['choices'][0]['message']['content'], usage

    def transcribe(self, audio, duration, language=None):
        boundary = uuid.uuid4().hex
        parts = []
        fields = {'model': self.config['model'], 'response_format': 'verbose_json', 'timestamp_granularities[]': 'segment'}
        if language:
            fields['language'] = language
        for key, value in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()+Path(audio).read_bytes()+b'\r\n')
        parts.append(f'--{boundary}--\r\n'.encode())
        result, usage = self.request('/audio/transcriptions', b''.join(parts), 'multipart/form-data; boundary='+boundary, ['audio'])
        if not isinstance(result.get('segments'), list):
            raise ValueError('Transcription service did not return segment timestamps')
        for segment in result['segments']:
            if not isinstance(segment.get('text'), str) or not all(isinstance(segment.get(k), (int,float)) and math.isfinite(segment[k]) for k in ('start','end')):
                raise ValueError('Invalid transcript segment')
            if not 0 <= segment['start'] < segment['end'] <= duration+0.25:
                segment['timing_valid'] = False
            else:
                segment['timing_valid'] = True
        return result, usage
