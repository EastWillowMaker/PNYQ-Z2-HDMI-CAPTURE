#!/usr/bin/env python3
"""Read-only, bounded process/board resource samples; run on the board."""
import argparse
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pid", type=int)
    parser.add_argument("--count", type=int, default=130)
    parser.add_argument("--interval", type=float, default=5)
    args = parser.parse_args()
    if args.pid <= 0 or args.count <= 0 or not 0 < args.interval <= 60:
        parser.error("positive PID/count and interval in (0,60] required")
    previous = None
    for index in range(args.count):
        now = time.monotonic()
        try:
            fields = Path(f"/proc/{args.pid}/stat").read_text().rsplit(")", 1)[1].split()
            ticks = int(fields[11]) + int(fields[12])
            start_ticks = int(fields[19])
            rss = int(fields[21]) * os.sysconf("SC_PAGE_SIZE")
        except FileNotFoundError:
            print(json.dumps(dict(event="process_missing", pid=args.pid,
                                  monotonic_seconds=now)), flush=True)
            break
        memory = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            if key in ("MemTotal", "MemAvailable", "CmaTotal", "CmaFree", "SwapFree"):
                memory[key + "_kib"] = int(value.split()[0])
        cpu = None
        if previous is not None:
            then, old_ticks, old_start = previous
            if start_ticks != old_start:
                raise RuntimeError("PID was reused; refusing to combine processes")
            cpu = 100 * (ticks - old_ticks) / os.sysconf("SC_CLK_TCK") / (now - then)
        print(json.dumps(dict(event="resource_sample", pid=args.pid,
                              monotonic_seconds=now, process_start_ticks=start_ticks,
                              process_cpu_percent_one_core=cpu, process_rss_bytes=rss,
                              memory=memory)), flush=True)
        previous = now, ticks, start_ticks
        if index + 1 < args.count:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
