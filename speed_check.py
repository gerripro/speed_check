"""Measure HTTP download throughput using ten sequential requests."""

import argparse
import math
import sys
from http.client import HTTPException
from time import perf_counter
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

REQUEST_COUNT = 10
CHUNK_SIZE = 64 * 1024


def http_url(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme in ("http", "https") and parsed.hostname:
            _ = parsed.port
            return value
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("expected an http:// or https:// URL")


def positive_timeout(value):
    try:
        timeout = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("timeout must be a positive number")
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number")
    return timeout


def download(url, timeout):
    """Return body bytes and elapsed seconds, including connection setup."""
    request = Request(url, headers={
        "User-Agent": "speed-check/1.0",
        "Accept-Encoding": "identity",
        "Cache-Control": "no-cache",
    })
    size = 0
    started = perf_counter()
    with urlopen(request, timeout=timeout) as response:
        if not 200 <= response.status < 300:
            raise ValueError(f"unexpected HTTP status: {response.status}")
        while chunk := response.read(CHUNK_SIZE):
            size += len(chunk)
        # Chunked responses are checked by http.client itself. For fixed-length
        # responses, detect a connection closed before all bytes arrived.
        length = response.headers.get("Content-Length")
        if not response.headers.get("Transfer-Encoding") and length is not None:
            if size != int(length):
                raise ValueError("incomplete response body")
    return size, perf_counter() - started


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Download a URL 10 times sequentially and report throughput."
    )
    parser.add_argument("url", type=http_url, help="HTTP(S) URL to download")
    parser.add_argument(
        "--timeout", type=positive_timeout, default=30.0,
        help="socket operation timeout in seconds (default: 30)",
    )
    args = parser.parse_args(argv)
    total_bytes = 0
    total_seconds = 0.0
    for number in range(1, REQUEST_COUNT + 1):
        try:
            size, elapsed = download(args.url, args.timeout)
        except (URLError, OSError, HTTPException, ValueError) as error:
            print(f"Request {number}/{REQUEST_COUNT} failed: {error}", file=sys.stderr)
            return 1
        total_bytes += size
        total_seconds += elapsed
        print(f"Request {number}/{REQUEST_COUNT}: {size} bytes in {elapsed:.3f} s")

    print(f"Average request time: {total_seconds / REQUEST_COUNT:.3f} s")
    print(f"Total downloaded: {total_bytes} bytes ({total_bytes / 1_000_000:.3f} MB)")
    print(f"Download speed: {total_bytes * 8 / total_seconds / 1_000_000:.3f} Mbps")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nMeasurement interrupted.", file=sys.stderr)
        sys.exit(130)
