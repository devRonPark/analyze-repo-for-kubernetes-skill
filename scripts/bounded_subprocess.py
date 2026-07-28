from __future__ import annotations

from dataclasses import dataclass
import subprocess
import threading
import time


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout: str
    stderr: str
    output_exceeded: bool
    timed_out: bool


def run(
    command: list[str],
    *,
    timeout: float,
    max_output_bytes: int,
) -> Result:
    if timeout <= 0:
        raise ValueError("timeout은 0보다 커야 합니다")
    if max_output_bytes <= 0:
        raise ValueError("max_output_bytes는 0보다 커야 합니다")

    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    output_exceeded = threading.Event()
    lock = threading.Lock()
    retained = 0
    stdout = bytearray()
    stderr = bytearray()

    def read_stream(stream, destination: bytearray) -> None:
        nonlocal retained
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            with lock:
                remaining = max_output_bytes - retained
                if remaining > 0:
                    kept = chunk[:remaining]
                    destination.extend(kept)
                    retained += len(kept)
                if len(chunk) > max(0, remaining):
                    output_exceeded.set()

    readers = (
        threading.Thread(
            target=read_stream,
            args=(process.stdout, stdout),
            daemon=True,
        ),
        threading.Thread(
            target=read_stream,
            args=(process.stderr, stderr),
            daemon=True,
        ),
    )
    for reader in readers:
        reader.start()

    deadline = time.monotonic() + timeout
    timed_out = False
    while process.poll() is None:
        if output_exceeded.wait(timeout=0.01):
            process.kill()
            break
        if time.monotonic() >= deadline:
            timed_out = True
            process.kill()
            break
    returncode = process.wait()
    for reader in readers:
        reader.join()
    process.stdout.close()
    process.stderr.close()

    return Result(
        returncode=returncode,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        output_exceeded=output_exceeded.is_set(),
        timed_out=timed_out,
    )
