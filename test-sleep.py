import time

for target in [0.1, 1, 3]:
    print(f"Sleeping for {target} seconds")
    target_ns = int(target * 1e9)
    for _ in range(5):
        before = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        time.sleep(target)
        after = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        actual_ns = after - before
        abs_error_s = (target_ns - actual_ns) / 1e9
        relative_error = abs_error_s / target
        print(f'target = {target}s, abs_error = {abs_error_s}s, relative_error = {relative_error}')