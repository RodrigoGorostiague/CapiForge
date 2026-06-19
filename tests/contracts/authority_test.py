import unittest

from runtime.shared.contracts import AuthorityError, JustificationPayload, validate_justification, validate_owner_write
from runtime.shared.ids import ActorIdentity, canonical_id


class AuthorityContractTest(unittest.TestCase):
    def test_canonical_ids_are_stable(self) -> None:
        self.assertEqual(canonical_id("task", "prj_1", "slug"), canonical_id("task", "prj_1", "slug"))

    def test_justification_requires_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "evidence"):
            validate_justification(JustificationPayload(summary="why", evidence_refs=(), expected_impact="impact"))

    def test_non_owner_canonical_write_is_rejected(self) -> None:
        actor = ActorIdentity(node_id="node_other", agent_id="agent_1", session_id="sess_1")
        with self.assertRaises(AuthorityError):
            validate_owner_write(owner_node_id="node_owner", actor=actor, canonical_write=True)


if __name__ == "__main__":
    unittest.main()
