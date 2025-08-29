import io
import sys
import json
import unittest

from src.logging import structured


class TestStructuredLogging(unittest.TestCase):
    def test_info_logs_json(self):
        buf = io.StringIO()
        old = sys.stdout
        try:
            sys.stdout = buf
            structured.info("agent_call", agent="Gemini", provider="google", corr_id="test123")
        finally:
            sys.stdout = old
        line = buf.getvalue().strip()
        rec = json.loads(line)
        self.assertEqual(rec["event"], "agent_call")
        self.assertEqual(rec["agent"], "Gemini")
        self.assertEqual(rec["provider"], "google")
        self.assertEqual(rec["corr_id"], "test123")


if __name__ == "__main__":
    unittest.main()

