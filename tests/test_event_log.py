from __future__ import annotations

import hashlib
import unittest

from liminal_gate.event_log import safe_form_diagnostics


class EventLogPrivacyTest(unittest.TestCase):
    def test_malformed_body_records_only_hash_and_size(self) -> None:
        body = b"\xffprivate-binary"
        self.assertEqual(
            {
                "request_body_sha256": hashlib.sha256(body).hexdigest(),
                "request_body_size": len(body),
            },
            safe_form_diagnostics(body),
        )


if __name__ == "__main__":
    unittest.main()
