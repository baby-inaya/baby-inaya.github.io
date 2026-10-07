"""Isolated HTTP checks: no project media or persistent preview server needed."""

from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

from serve import RangeRequestHandler


class QuietHandler(RangeRequestHandler):
    def log_message(self, format, *args):
        pass


class PreviewServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.parent = Path(cls.temporary.name)
        cls.root = cls.parent / 'site'
        cls.root.mkdir()
        cls.payload = bytes(range(256)) * 1024
        (cls.root / 'clip #1.mp4').write_bytes(cls.payload)
        (cls.root / 'empty.mp4').write_bytes(b'')
        (cls.root / 'index.html').write_text('<h1>Preview</h1>', encoding='utf-8')
        (cls.parent / 'outside.txt').write_text('outside the document root', encoding='utf-8')
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(cls.root)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temporary.cleanup()

    def request(self, path='/clip%20%231.mp4', method='GET', headers=None):
        connection = HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            # HTTP field names are case-insensitive; preserve HTTPMessage's lookup.
            return response.status, response.headers, response.read()
        finally:
            connection.close()

    def test_full_get_and_head(self):
        status, headers, body = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(body, self.payload)
        self.assertEqual(headers['Content-Type'], 'video/mp4')
        self.assertEqual(headers['Content-Length'], str(len(self.payload)))
        self.assertEqual(headers['Accept-Ranges'], 'bytes')
        status, head_headers, body = self.request(method='HEAD')
        self.assertEqual(status, 200)
        self.assertEqual(body, b'')
        self.assertEqual(head_headers['Content-Length'], headers['Content-Length'])

    def test_closed_open_suffix_and_clamped_ranges(self):
        size = len(self.payload)
        examples = [('bytes=8-19', 8, 19), ('bytes=200000-', 200000, size - 1),
                    ('bytes=-19', size - 19, size - 1), ('bytes=262140-999999', 262140, size - 1),
                    ('bytes=-999999', 0, size - 1), ('bytes=0-0', 0, 0)]
        for value, start, end in examples:
            with self.subTest(range=value):
                status, headers, body = self.request(headers={'Range': value})
                self.assertEqual(status, 206)
                self.assertEqual(headers['Content-Range'], f'bytes {start}-{end}/{size}')
                self.assertEqual(headers['Content-Length'], str(end - start + 1))
                self.assertEqual(headers['Content-Type'], 'video/mp4')
                self.assertEqual(body, self.payload[start:end + 1])

    def test_range_head_has_get_headers_without_body(self):
        status, headers, body = self.request(method='HEAD', headers={'Range': 'bytes=10-29'})
        self.assertEqual(status, 206)
        self.assertEqual(headers['Content-Range'], f'bytes 10-29/{len(self.payload)}')
        self.assertEqual(headers['Content-Length'], '20')
        self.assertEqual(body, b'')

    def test_unsatisfiable_and_empty_ranges(self):
        for value in ('bytes=262144-', 'bytes=20-10', 'bytes=-0'):
            with self.subTest(range=value):
                status, headers, body = self.request(headers={'Range': value})
                self.assertEqual(status, 416)
                self.assertEqual(headers['Content-Range'], f'bytes */{len(self.payload)}')
                self.assertEqual(headers['Content-Length'], '0')
                self.assertEqual(body, b'')
        status, headers, body = self.request('/empty.mp4', headers={'Range': 'bytes=0-'})
        self.assertEqual(status, 416)
        self.assertEqual(headers['Content-Range'], 'bytes */0')
        self.assertEqual(body, b'')

    def test_unsupported_or_malformed_ranges_fall_back_to_full_response(self):
        for value in ('bytes=0-2,8-9', 'bytes=not-a-range', 'items=1-2', 'bytes=-'):
            with self.subTest(range=value):
                status, headers, body = self.request(headers={'Range': value})
                self.assertEqual(status, 200)
                self.assertEqual(body, self.payload)
                self.assertNotIn('Content-Range', headers)

    def test_if_range_and_date_preconditions(self):
        _, headers, _ = self.request(method='HEAD')
        modified = headers['Last-Modified']
        status, _, body = self.request(headers={'Range': 'bytes=4-8', 'If-Range': modified})
        self.assertEqual((status, body), (206, self.payload[4:9]))
        status, _, body = self.request(headers={'Range': 'bytes=4-8', 'If-Range': 'Wed, 01 Jan 1997 00:00:00 GMT'})
        self.assertEqual((status, body), (200, self.payload))
        status, _, body = self.request(headers={'Range': 'bytes=4-8', 'If-Modified-Since': modified})
        self.assertEqual((status, body), (304, b''))

    def test_index_missing_files_and_traversal(self):
        status, headers, body = self.request('/')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'text/html')
        self.assertIn(b'Preview', body)
        for path in ('/missing.mp4', '/../outside.txt', '/%2e%2e/outside.txt'):
            with self.subTest(path=path):
                status, _, body = self.request(path, headers={'Range': 'bytes=0-5'})
                self.assertEqual(status, 404)
                self.assertNotIn(b'outside the document root', body)


if __name__ == '__main__':
    unittest.main()
