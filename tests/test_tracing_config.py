"""Check tracing configuration in fresh processes without sending any traces."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TracingConfigTests(unittest.TestCase):
    def inspect_config(self, overrides=None, *, env_file=True):
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("LANGSMITH_", "LANGCHAIN_"))
        }
        environment.update(overrides or {})
        with tempfile.TemporaryDirectory() as folder:
            if env_file:
                Path(folder, ".env").write_text(
                    "LANGSMITH_TRACING=true\n"
                    "LANGSMITH_API_KEY=test-key\n"
                    "LANGSMITH_PROJECT=test-project\n",
                    encoding="utf-8",
                )
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    """
import json
import os
from rag_library.main import app
from langsmith import utils
print(json.dumps({
    "enabled": utils.tracing_is_enabled(),
    "key_present": bool(os.environ.get("LANGSMITH_API_KEY")),
    "project": os.environ.get("LANGSMITH_PROJECT"),
}))
""",
                ],
                cwd=folder,
                env=environment,
                capture_output=True,
                text=True,
                check=True,
                timeout=20,
            )
            return json.loads(result.stdout)

    def test_app_loads_tracing_from_dotenv(self):
        self.assertEqual(
            self.inspect_config(),
            {"enabled": True, "key_present": True, "project": "test-project"},
        )

    def test_explicit_process_opt_out_overrides_dotenv(self):
        result = self.inspect_config(
            {"LANGSMITH_TRACING": "false", "LANGSMITH_PROJECT": "exported-project"}
        )
        self.assertFalse(result["enabled"])
        self.assertEqual(result["project"], "exported-project")

    def test_tracing_stays_disabled_without_configuration(self):
        self.assertEqual(
            self.inspect_config(env_file=False),
            {"enabled": False, "key_present": False, "project": None},
        )
