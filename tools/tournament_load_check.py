"""Read-only HTTP load probe for a local/staging deployment, with measured percentiles.

python tools/tournament_load_check.py --url http://127.0.0.1:8000/ --requests 4000 --concurrency 100
This probes HTTP requests, not 4000 authenticated people submitting at once.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import statistics
import time
import urllib.request
import urllib.error


def main():
    parser = argparse.ArgumentParser(description='Đo tải đọc HTTP trên local/staging trước giải.')
    parser.add_argument('--url', required=True)
    parser.add_argument('--requests', type=int, default=4000)
    parser.add_argument('--concurrency', type=int, default=100)
    parser.add_argument('--cookie-file', help='File chứa cookie của tài khoản diễn tập, không đưa vào Git.')
    parser.add_argument('--output', default='private-exports/load-report.json')
    args = parser.parse_args()
    if not 1 <= args.requests <= 100000 or not 1 <= args.concurrency <= 4000:
        parser.error('requests: 1–100000; concurrency: 1–4000')
    headers = {'Cookie': Path(args.cookie_file).read_text().strip()} if args.cookie_file else {}

    def request(_):
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(urllib.request.Request(args.url, headers=headers), timeout=30) as response:
                response.read()
                code = response.status
        except urllib.error.HTTPError as exc:
            code = exc.code
        except OSError:
            code = 'network_error'
        return str(code), (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(request, range(args.requests)))
    elapsed = time.perf_counter() - start
    timings = sorted(value for _, value in results)
    percentile = lambda fraction: timings[min(len(timings) - 1, int((len(timings) - 1) * fraction))]
    report = {'url': args.url, 'requests': len(results), 'concurrency': args.concurrency,
              'statuses': dict(Counter(status for status, _ in results)), 'seconds': round(elapsed, 2),
              'requests_per_second': round(len(results) / elapsed, 2), 'p50_ms': round(statistics.median(timings), 2),
              'p95_ms': round(percentile(.95), 2), 'p99_ms': round(percentile(.99), 2)}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
