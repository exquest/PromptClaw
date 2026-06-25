"""Import-isolation guarantee (Phase 3b): promptclaw.coherence must stay light.

sdp-cli (and any host) imports promptclaw.coherence to govern runs; that import must NOT drag
in the orchestrator, the CLI, or CypherClaw's music libraries. Verified in a subprocess for a
clean import state.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest

_HEAVY = ("promptclaw.orchestrator", "promptclaw.cli", "librosa", "partitura", "cypherclaw")


class TestCoherenceImportIsolation(unittest.TestCase):
    def test_importing_coherence_stays_light(self):
        code = textwrap.dedent(
            f"""
            import sys
            import promptclaw.coherence
            from promptclaw.coherence import open_session, CoherenceSession, NullCoherenceSession, Verdict
            heavy = [m for m in {_HEAVY!r} if m in sys.modules]
            sys.exit("loaded: " + ",".join(heavy) if heavy else 0)
            """
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr).strip())


if __name__ == "__main__":
    unittest.main()
