import unittest

from src.coordination import api


class TestJobsAPI(unittest.TestCase):
    def test_submit_and_get_and_cancel(self):
        # Submit
        resp = api.submit_job("unit_test", {"x": 1})
        self.assertIn("id", resp)
        jid = resp["id"]
        self.assertEqual(resp["status"], "queued")

        # Get
        get = api.get_job(jid)
        self.assertEqual(get.get("id"), jid)
        self.assertIn(get.get("status"), ("queued", "running", "done", "error", "canceled"))

        # Cancel
        cancel = api.cancel_job(jid)
        self.assertEqual(cancel.get("id"), jid)
        self.assertEqual(cancel.get("status"), "canceled")

        # Get unknown
        self.assertEqual(api.get_job("nope").get("error"), "not_found")


if __name__ == "__main__":
    unittest.main()

