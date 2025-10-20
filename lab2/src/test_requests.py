import sys
import threading
import time
import statistics
import random
import os
from collections import Counter
import requests


def usage_and_exit():
    print(__doc__)
    sys.exit(1)


def list_files(base_dir):
    files = []
    for root, _, filenames in os.walk(base_dir):
        for f in filenames:
            rel_path = os.path.relpath(os.path.join(root, f), base_dir)
            files.append(rel_path.replace("\\", "/"))
    return files


def worker(idx, base_url, files, results, timeout=10):
    try:
        target = random.choice(files)
        url = f"{base_url.rstrip('/')}/{target}"
        start = time.time()
        r = requests.get(url, timeout=timeout)
        elapsed = time.time() - start
        results[idx] = (r.status_code, elapsed, None, target)
    except Exception as e:
        elapsed = time.time() - start if 'start' in locals() else 0.0
        results[idx] = (None, elapsed, str(e), None)


def main():
    if len(sys.argv) < 5:
        print("Usage: python test_requests.py TOTAL INTERVAL AFTER_N CONTENT_DIR [EXTRA_DELAY]")
        print("Example: python test_requests.py 100 0.01 50 lab2/content 0.5")
        sys.exit(1)

    try:
        total = int(sys.argv[1])
        interval = float(sys.argv[2])
        after_n = int(sys.argv[3])
        content_dir = sys.argv[4]
        extra_delay = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0
    except Exception as e:
        print("Invalid arguments:", e)
        usage_and_exit()

    base_url = "http://127.0.0.1:8080"
    files = list_files(content_dir)
    if not files:
        print("❌ No files found in directory:", content_dir)
        sys.exit(1)

    print(f"Found {len(files)} files under {content_dir}")
    print(f"Starting {total} random requests to {base_url}")
    print(f" - interval between starts: {interval}s")
    print(f" - after {after_n} started requests apply extra delay: {extra_delay}s\n")

    results = [None] * total
    threads = []
    overall_start = time.time()
    started = 0

    for i in range(total):
        t = threading.Thread(target=worker, args=(i, base_url, files, results))
        t.daemon = True
        t.start()
        threads.append(t)
        started += 1

        if started >= after_n:
            sleep_time = interval + extra_delay
        else:
            sleep_time = interval
        if i != total - 1:
            time.sleep(sleep_time)

    for t in threads:
        t.join(timeout=30)

    total_time = time.time() - overall_start

    # --- ANALYTICS ---
    status_counter = Counter()
    latencies = []
    errors = 0

    for entry in results:
        if entry is None:
            errors += 1
            continue
        status, elapsed, err, _ = entry
        if err:
            status_counter["ERROR"] += 1
        else:
            status_counter[status] += 1
            latencies.append(elapsed)

    succeeded = status_counter.get(200, 0)
    rate_limited = status_counter.get(429, 0)

    print("\n--- RESULTS ---")
    print(f"Total requests attempted: {total}")
    print(f"Total responses: {sum(status_counter.values())}")
    print(f"Total time (wall-clock): {total_time:.3f} s")
    print(f"Throughput (requests/sec): {total / total_time:.2f}")

    print("\nStatus summary:")
    for k, v in status_counter.most_common():
        print(f"  {k}: {v}")
    print(f"Errors: {errors}")

    if latencies:
        print("\nLatency (s):")
        print(f"  count: {len(latencies)}")
        print(f"  min:   {min(latencies):.4f}")
        print(f"  avg:   {statistics.mean(latencies):.4f}")
        print(f"  median:{statistics.median(latencies):.4f}")
        print(f"  max:   {max(latencies):.4f}")
    else:
        print("No successful latencies to report.")

    print("\nAcceptance:")
    print(f"  accepted (200): {succeeded} ({(succeeded/total*100):.2f}%)")
    print(f"  rate-limited (429): {rate_limited} ({(rate_limited/total*100):.2f}%)")
    others = sum(v for k, v in status_counter.items() if k not in (200, 429, "ERROR"))
    print(f"  other status codes: {others}")


if __name__ == "__main__":
    main()
