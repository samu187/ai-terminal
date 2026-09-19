import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from ai_terminal.cli import ZSHRC_BLOCK


@unittest.skipUnless(shutil.which("zsh"), "Zsh is required")
class AutofillTests(unittest.TestCase):
    def test_shell_escapes_survive_autofill(self):
        command = r"""printf '%s\n' hello | awk '{printf "%s\n", $0}'"""
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "ai"
            executable.write_text(
                "#!/bin/sh\ncat <<'JSON'\n"
                + json.dumps({"message": None, "command": command})
                + "\nJSON\n"
            )
            executable.chmod(0o755)
            result = subprocess.run(
                ["zsh", "-f", "-c", ZSHRC_BLOCK
                 + '\nai test\nread -rz queued\nprint -rn -- "$queued"\n'],
                env={**os.environ, "PATH": directory + ":" + os.environ["PATH"]},
                capture_output=True, text=True, check=True,
            )
        self.assertEqual(result.stdout, command)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
