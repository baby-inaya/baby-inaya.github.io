"""Preview the memory book locally, including seeking within large video files.

Run ``python scripts/serve.py`` and open http://127.0.0.1:8000.
The served directory is always the repository root, regardless of the current
working directory. Only the Python standard library is required.
"""

import argparse
import datetime
import email.utils
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent


class UnsatisfiableRange(ValueError):
    """A valid byte-range request cannot select any bytes of this file."""


def parse_range(value, size):
    """Return one inclusive (start, end) range, or None to send the full file.

    HTTP permits servers to ignore unsupported ranges. We do that for malformed
    headers and multipart requests; ordinary closed, open and suffix byte ranges
    are supported. Empty files and unsatisfiable offsets return HTTP 416.
    """
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', value.strip(), re.IGNORECASE)
    if not match or not any(match.groups()):
        return None
    first, last = match.groups()
    try:
        if first:
            start = int(first)
            end = int(last) if last else size - 1
            if start >= size or end < start:
                raise UnsatisfiableRange()
            return start, min(end, size - 1)
        suffix_length = int(last)
        if not suffix_length or not size:
            raise UnsatisfiableRange()
        return max(0, size - suffix_length), size - 1
    except ValueError as error:
        if isinstance(error, UnsatisfiableRange):
            raise
        # Python rejects unreasonable integer lengths; ignore such a header.
        return None


class RangeRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler with bounded streaming of single byte ranges."""

    def end_headers(self):
        self.send_header('Accept-Ranges', 'bytes')
        # Revalidate local edits instead of showing a stale stylesheet or catalog.
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def send_head(self):
        self._range_remaining = None
        requested_range = self.headers.get('Range')
        path = self.translate_path(self.path)
        if not requested_range or os.path.isdir(path):
            return super().send_head()
        try:
            source = open(path, 'rb')
        except OSError:
            return super().send_head()

        try:
            stat = os.fstat(source.fileno())
            modified = self.date_time_string(stat.st_mtime)
            if_range = self.headers.get('If-Range')
            if if_range and if_range != modified:
                # We do not issue ETags. An unknown validator requires the full
                # current representation, never a range from a changed file.
                source.close()
                return super().send_head()

            if self._not_modified(stat.st_mtime):
                source.close()
                self.send_response(HTTPStatus.NOT_MODIFIED)
                self.end_headers()
                return None

            try:
                selected = parse_range(requested_range, stat.st_size)
            except UnsatisfiableRange:
                source.close()
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header('Content-Range', f'bytes */{stat.st_size}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return None
            if selected is None:
                source.close()
                return super().send_head()

            start, end = selected
            self._range_remaining = end - start + 1
            source.seek(start)
            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header('Content-Type', self.guess_type(path))
            self.send_header('Content-Range', f'bytes {start}-{end}/{stat.st_size}')
            self.send_header('Content-Length', str(self._range_remaining))
            self.send_header('Last-Modified', modified)
            self.end_headers()
            return source
        except BaseException:
            source.close()
            raise

    def _not_modified(self, mtime):
        """Apply the same date precondition as SimpleHTTPRequestHandler."""
        value = self.headers.get('If-Modified-Since')
        if not value or self.headers.get('If-None-Match'):
            return False
        try:
            since = email.utils.parsedate_to_datetime(value)
            if since.tzinfo is None:
                since = since.replace(tzinfo=datetime.timezone.utc)
            return int(mtime) <= since.timestamp()
        except (TypeError, ValueError, OverflowError):
            return False

    def copyfile(self, source, outputfile):
        if self._range_remaining is None:
            return super().copyfile(source, outputfile)
        remaining = self._range_remaining
        while remaining:
            block = source.read(min(64 * 1024, remaining))
            if not block:
                break
            outputfile.write(block)
            remaining -= len(block)

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Browsers routinely cancel an old video request when seeking.
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000, help='Local preview port (default: 8000)')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    handler = partial(RangeRequestHandler, directory=str(ROOT))
    with ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
        print(f'Memory book preview: http://127.0.0.1:{args.port}', flush=True)
        print(f'Serving {ROOT}\nPress Ctrl+C to stop.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('\nPreview stopped.')


if __name__ == '__main__':
    main()
