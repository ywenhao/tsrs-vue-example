"""Measure a fresh compiler's wall time and concurrently sampled process-tree RSS.

Linux/WSL only; Python standard library only. RSS includes shared pages in each
process, so this is the sum of RSS, not unique physical memory or a PSS measure.
"""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def processes():
    result = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            text = (entry / 'stat').read_text()
            fields = text[text.rfind(')') + 2:].split()
            result[int(entry.name)] = {
                'parent': int(fields[1]),
                'group': int(fields[2]),
                'start': int(fields[19]),
                'rss': max(0, int(fields[21])) * os.sysconf('SC_PAGE_SIZE'),
                'state': fields[0],
            }
        except (OSError, ValueError, IndexError):
            continue
    return result


def owned_processes(snapshot, leader, known):
    owned = {
        pid for pid, item in snapshot.items()
        if item['group'] == leader or known.get(pid) == item['start']
    }
    while True:
        children = {pid for pid, item in snapshot.items() if item['parent'] in owned}
        expanded = owned | children
        if expanded == owned:
            break
        owned = expanded
    for pid in owned:
        known[pid] = snapshot[pid]['start']
    return owned


def cleanup(leader, known):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        snapshot = processes()
        owned = owned_processes(snapshot, leader, known)
        if not owned:
            return
        for pid in owned:
            if snapshot[pid]['state'] == 'Z':
                continue
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        if sig == signal.SIGTERM:
            time.sleep(0.1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--log', required=True)
    parser.add_argument('--cwd', required=True)
    parser.add_argument('--interval-ms', type=float, default=25)
    parser.add_argument('--timeout-seconds', type=float, default=600)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not Path('/proc/self/stat').is_file() or not command or args.interval_ms <= 0:
        parser.error('Linux/WSL /proc, a command, and a positive sampling interval are required')

    process = None
    known = {}
    peak = 0
    max_processes = 0
    samples = 0
    interrupted = False
    timed_out = False
    start = time.perf_counter()
    try:
        with open(args.log, 'w') as log:
            process = subprocess.Popen(
                command, cwd=args.cwd, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            )
            while True:
                snapshot = processes()
                owned = owned_processes(snapshot, process.pid, known)
                peak = max(peak, sum(snapshot[pid]['rss'] for pid in owned))
                max_processes = max(max_processes, len(owned))
                samples += 1
                if process.poll() is not None:
                    break
                if time.perf_counter() - start > args.timeout_seconds:
                    timed_out = True
                    break
                time.sleep(args.interval_ms / 1000)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        wall_ms = (time.perf_counter() - start) * 1000
        if process is not None:
            cleanup(process.pid, known)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        report = {
            'exitCode': process.returncode if process else None,
            'interrupted': interrupted,
            'timedOut': timed_out,
            'wallMs': wall_ms,
            'peakRssBytes': peak,
            'maxProcesses': max_processes,
            'samples': samples,
            'sampleIntervalMs': args.interval_ms,
            'measurement': 'Peak of simultaneously sampled RSS summed over the compiler process tree; shared pages may be counted more than once; monitor excluded.',
            'command': command,
        }
        Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
    return 130 if interrupted else 0


if __name__ == '__main__':
    sys.exit(main())
