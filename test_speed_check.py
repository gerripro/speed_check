import contextlib
import io
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import speed_check


BODY = b"x" * (speed_check.CHUNK_SIZE * 2 + 17)


class Handler(BaseHTTPRequestHandler):
    completed = 0

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/missing":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        if self.path == "/broken":
            self.wfile.write(BODY[:10])
            self.close_connection = True
            return
        self.wfile.write(BODY[:100])
        self.wfile.flush()
        time.sleep(0.01)
        self.wfile.write(BODY[100:])
        Handler.completed += 1


class SpeedCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_ten_complete_downloads(self):
        Handler.completed = 0
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = speed_check.main([self.url])
        self.assertEqual(code, 0)
        self.assertEqual(Handler.completed, 10)
        self.assertEqual(output.getvalue().count("Request "), 10)
        self.assertIn(f"Total downloaded: {10 * len(BODY)} bytes", output.getvalue())
        self.assertIn("Download speed:", output.getvalue())

    def test_download_waits_for_body(self):
        size, seconds = speed_check.download(self.url, 2)
        self.assertEqual(size, len(BODY))
        self.assertGreaterEqual(seconds, 0.01)

    def test_http_error_and_truncated_body_fail_without_summary(self):
        for path in ("/missing", "/broken"):
            with self.subTest(path=path):
                output, errors = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    code = speed_check.main([self.url + path])
                self.assertEqual(code, 1)
                self.assertIn("Request 1/10 failed", errors.getvalue())
                self.assertNotIn("Download speed:", output.getvalue())

    def test_invalid_arguments(self):
        for args in (["file:///tmp/file"], [self.url, "--timeout", "nan"],
                     [self.url, "--timeout", "0"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    speed_check.main(args)
                self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
