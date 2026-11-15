import http.client
import json
import tempfile
import threading
import unittest
from http.server import HTTPServer
from edie.api import handler


class APITest(unittest.TestCase):
    def test_auth_and_persistent_records(self):
        with tempfile.TemporaryDirectory() as root:
            token = 'test-only-token-' * 3
            server = HTTPServer(('127.0.0.1', 0), handler(root, token))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def request(method, path, body=None, auth=True):
                conn = http.client.HTTPConnection(*server.server_address)
                headers = {'Authorization': 'Bearer '+token} if auth else {}
                conn.request(method, path, json.dumps(body) if body is not None else None, headers)
                response = conn.getresponse()
                result = response.status, json.loads(response.read())
                conn.close()
                return result
            try:
                self.assertEqual(request('GET', '/projects', auth=False)[0], 401)
                status, project = request('POST', '/projects', {'name': 'Fixture'})
                self.assertEqual(status, 201)
                status, listing = request('GET', '/projects')
                self.assertEqual(listing[0]['id'], project['id'])
                self.assertEqual(request('POST', '/jobs', {'project': project['id'], 'brief': {}})[0], 400)
                self.assertEqual(request('GET', '/unknown')[0], 404)
                self.assertEqual(request('POST', '/jobs', {'project': project['id'], 'brief': []})[0], 400)
                self.assertEqual(request('POST', '/projects', [1, 2])[0], 400)
                self.assertEqual(request('POST', '/projects', {'name': {}})[0], 400)
            finally:
                server.shutdown()
                thread.join()
                server.server_close()
