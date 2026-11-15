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
                self.assertEqual(request('GET', '/jobs', auth=False)[0], 401)
                brief = dict(goal='Fixture', audience='Editor', format='16:9', duration=5, language='en')
                status, job = request('POST', '/jobs', {'brief': brief})
                self.assertEqual(status, 201)
                status, listing = request('GET', '/jobs')
                self.assertEqual(listing[0]['id'], job['id'])
                self.assertNotIn('project', listing[0])
                self.assertEqual(request('POST', '/jobs', {'brief': {}})[0], 400)
                self.assertEqual(request('POST', '/jobs', {'brief': brief, 'project': 'old'})[0], 400)
                self.assertEqual(request('POST', '/jobs', [1, 2])[0], 400)
                self.assertEqual(request('POST', '/projects', {'name': 'Removed'})[0], 404)
                self.assertEqual(request('GET', '/projects')[0], 404)
            finally:
                server.shutdown()
                thread.join()
                server.server_close()
