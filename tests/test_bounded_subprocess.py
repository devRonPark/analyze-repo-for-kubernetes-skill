from pathlib import Path
import sys
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bounded_subprocess


class BoundedSubprocessTests(unittest.TestCase):
    def test_output_over_limit_is_capped_and_process_is_stopped(self):
        result = bounded_subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.write('x' * 1000000)",
            ],
            timeout=5,
            max_output_bytes=1024,
        )

        self.assertTrue(result.output_exceeded)
        self.assertFalse(result.timed_out)
        self.assertLessEqual(
            len(result.stdout.encode("utf-8"))
            + len(result.stderr.encode("utf-8")),
            1024,
        )

    def test_timeout_stops_process_without_unbounded_output(self):
        result = bounded_subprocess.run(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(10)",
            ],
            timeout=0.05,
            max_output_bytes=1024,
        )

        self.assertTrue(result.timed_out)
        self.assertFalse(result.output_exceeded)

    def test_timeout_kills_descendant_holding_output_pipe(self):
        started = time.monotonic()

        result = bounded_subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import subprocess,sys,time;"
                    "subprocess.Popen([sys.executable,'-c',"
                    "'import time; time.sleep(10)']);"
                    "time.sleep(10)"
                ),
            ],
            timeout=0.05,
            max_output_bytes=1024,
        )

        self.assertTrue(result.timed_out)
        self.assertLess(time.monotonic() - started, 1.0)


if __name__ == "__main__":
    unittest.main()
