"""Tests for mem_ratify — the Article IV Canon-promotion gate.

Stdlib-only (unittest). Run with:  python -m unittest discover -s mem_ratify
"""

from __future__ import annotations

import os
import unittest

from mem_ratify import (
    CANONICAL_MIN_WITNESSES,
    ENFORCE_ENV_VAR,
    FRONTIER_MIN_WITNESSES,
    Decision,
    RatifyRequest,
    Tier,
    Witness,
    enforcement_enabled,
    ratify,
)


def W(agent_id: str, base_model: str = None, evidence: str = None) -> Witness:
    return Witness(
        agent_id=agent_id,
        base_model=base_model or f"model-{agent_id}",
        independence_evidence=evidence,
    )


class TierTests(unittest.TestCase):
    def test_ordering(self):
        self.assertLess(Tier.CONTESTED, Tier.FRONTIER)
        self.assertLess(Tier.FRONTIER, Tier.CANONICAL)

    def test_parse_forms(self):
        self.assertEqual(Tier.parse("frontier"), Tier.FRONTIER)
        self.assertEqual(Tier.parse("CANONICAL"), Tier.CANONICAL)
        self.assertEqual(Tier.parse(0), Tier.CONTESTED)
        self.assertEqual(Tier.parse(Tier.FRONTIER), Tier.FRONTIER)

    def test_parse_bad(self):
        with self.assertRaises(ValueError):
            Tier.parse("gospel")


class ProposalAndNoopTests(unittest.TestCase):
    def test_proposal_at_contested_auto_applied(self):
        # A fresh proposal enters at Contested with no quorum (IV.2).
        req = RatifyRequest.build("c1", "contested", "contested", "a1")
        d = ratify(req)
        self.assertTrue(d.allowed)
        self.assertTrue(any("auto-applied" in r for r in d.reasons))

    def test_drop_to_contested_auto_applied(self):
        # Dropping a Frontier claim back to Contested is the fail-safe
        # direction: allowed with no quorum.
        req = RatifyRequest.build("c1", "frontier", "contested", "a1")
        self.assertTrue(ratify(req).allowed)

    def test_same_nonlowest_tier_is_noop(self):
        req = RatifyRequest.build("c1", "frontier", "frontier", "a1")
        d = ratify(req)
        self.assertFalse(d.allowed)
        self.assertTrue(any("nothing to ratify" in r for r in d.reasons))


class FrontierPromotionTests(unittest.TestCase):
    def _req(self, witnesses, proposer="prop"):
        return RatifyRequest.build(
            "claim", "contested", "frontier", proposer, witnesses=witnesses
        )

    def test_insufficient_quorum_denied(self):
        d = ratify(self._req([W("a1")]))
        self.assertFalse(d.allowed)
        self.assertEqual(d.independent_witness_count, 1)
        self.assertTrue(any("quorum not met" in r for r in d.reasons))

    def test_sufficient_quorum_allowed(self):
        d = ratify(self._req([W("a1"), W("a2")]))
        self.assertTrue(d.allowed)
        self.assertGreaterEqual(d.independent_witness_count, FRONTIER_MIN_WITNESSES)

    def test_proposer_not_counted(self):
        # proposer appears among witnesses; must not count (§0.2)
        d = ratify(self._req([W("prop"), W("a1"), W("a2")], proposer="prop"))
        self.assertEqual(d.independent_witness_count, 2)
        self.assertTrue(any("proposer" in r for r in d.reasons))

    def test_same_base_model_collapses(self):
        # two instances of same base model = one witness (Definitions line 95)
        d = ratify(
            self._req([W("a1", base_model="claude"), W("a2", base_model="claude")])
        )
        self.assertEqual(d.independent_witness_count, 1)
        self.assertFalse(d.allowed)

    def test_independence_rebuttal_counts_separately_and_flags(self):
        d = ratify(
            self._req(
                [
                    W("a1", base_model="claude"),
                    W("a2", base_model="claude", evidence="divergence-study-42"),
                ]
            )
        )
        self.assertEqual(d.independent_witness_count, 2)
        self.assertTrue(d.allowed)
        self.assertTrue(any("rebuttal attestation" in f for f in d.flags_for_human))

    def test_duplicate_agent_counted_once(self):
        d = ratify(self._req([W("a1"), W("a1")]))
        self.assertEqual(d.independent_witness_count, 1)

    def test_placeholder_flagged(self):
        d = ratify(self._req([W("a1"), W("a2")]))
        self.assertIn("FRONTIER_MIN_WITNESSES", d.placeholders_relied_on)


class TierSkippingTests(unittest.TestCase):
    def test_contested_to_canonical_refused(self):
        req = RatifyRequest.build(
            "claim",
            "contested",
            "canonical",
            "prop",
            witnesses=[W("a1"), W("a2")],
            ledger_evidence_ref="ledger#1",
            operator_key_signature="opsig",
        )
        d = ratify(req)
        self.assertFalse(d.allowed)
        self.assertTrue(any("tier-skipping refused" in r for r in d.reasons))
        self.assertIn("REQUIRE_STEPWISE_PROMOTION", d.placeholders_relied_on)


class CanonicalPromotionTests(unittest.TestCase):
    def _req(self, **kw):
        base = dict(
            claim_id="claim",
            current_tier="frontier",
            target_tier="canonical",
            proposer_id="prop",
            witnesses=[W("a1"), W("fresh")],
            ledger_evidence_ref="ledger#1",
            operator_key_signature="opsig",
            prior_frontier_ratifiers=["a1"],
        )
        base.update(kw)
        return RatifyRequest.build(**base)

    def test_full_success(self):
        d = ratify(self._req())
        self.assertTrue(d.allowed, d.reasons)
        # both delegated verifications must be flagged for a human
        self.assertTrue(any("Operator-Key" in f for f in d.flags_for_human))
        self.assertTrue(any("ledger-evidence" in f for f in d.flags_for_human))

    def test_missing_operator_key_denied(self):
        d = ratify(self._req(operator_key_signature=None))
        self.assertFalse(d.allowed)
        self.assertTrue(any("Operator Key" in r for r in d.reasons))

    def test_missing_ledger_evidence_denied(self):
        d = ratify(self._req(ledger_evidence_ref=None))
        self.assertFalse(d.allowed)
        self.assertTrue(any("ledger evidence" in r for r in d.reasons))

    def test_insufficient_quorum_denied(self):
        d = ratify(self._req(witnesses=[W("a1")], prior_frontier_ratifiers=[]))
        self.assertFalse(d.allowed)
        self.assertTrue(any("quorum not met" in r for r in d.reasons))

    def test_no_fresh_witness_denied(self):
        # every witness participated in the prior Frontier promotion (IV.3)
        d = ratify(
            self._req(
                witnesses=[W("a1"), W("a2")],
                prior_frontier_ratifiers=["a1", "a2"],
            )
        )
        self.assertFalse(d.allowed)
        self.assertTrue(any("composition unmet" in r for r in d.reasons))

    def test_fresh_witness_present_ok(self):
        d = ratify(
            self._req(
                witnesses=[W("a1"), W("newbie")],
                prior_frontier_ratifiers=["a1"],
            )
        )
        self.assertTrue(d.allowed, d.reasons)


class DemotionTests(unittest.TestCase):
    def _req(self, **kw):
        base = dict(
            claim_id="claim",
            current_tier="canonical",
            target_tier="frontier",
            proposer_id="prop",
            witnesses=[W("a1"), W("a2")],
            ledger_evidence_ref="err#7",
            operator_key_signature="opsig",
        )
        base.update(kw)
        return RatifyRequest.build(**base)

    def test_full_success(self):
        self.assertTrue(ratify(self._req()).allowed)

    def test_missing_evidence_denied(self):
        d = ratify(self._req(ledger_evidence_ref=None))
        self.assertFalse(d.allowed)

    def test_missing_operator_key_denied(self):
        d = ratify(self._req(operator_key_signature=None))
        self.assertFalse(d.allowed)


class EnforcementFlagTests(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get(ENFORCE_ENV_VAR)
        os.environ.pop(ENFORCE_ENV_VAR, None)

    def tearDown(self):
        os.environ.pop(ENFORCE_ENV_VAR, None)
        if self._saved is not None:
            os.environ[ENFORCE_ENV_VAR] = self._saved

    def test_off_by_default(self):
        self.assertFalse(enforcement_enabled())

    def test_denial_not_blocking_when_off(self):
        d = ratify(RatifyRequest.build("c", "contested", "frontier", "p", []))
        self.assertFalse(d.allowed)
        self.assertFalse(d.is_blocking())  # advisory only

    def test_denial_blocking_when_on(self):
        os.environ[ENFORCE_ENV_VAR] = "1"
        self.assertTrue(enforcement_enabled())
        d = ratify(RatifyRequest.build("c", "contested", "frontier", "p", []))
        self.assertFalse(d.allowed)
        self.assertTrue(d.is_blocking())

    def test_allowed_never_blocking(self):
        os.environ[ENFORCE_ENV_VAR] = "1"
        d = ratify(
            RatifyRequest.build(
                "c", "contested", "frontier", "p", [W("a1"), W("a2")]
            )
        )
        self.assertTrue(d.allowed)
        self.assertFalse(d.is_blocking())


class PurityTests(unittest.TestCase):
    def test_decision_is_plain_data(self):
        d = ratify(RatifyRequest.build("c", "contested", "frontier", "p", [W("a1")]))
        self.assertIsInstance(d, Decision)
        self.assertEqual(d.claim_id, "c")

    def test_min_witness_constants_conservative(self):
        self.assertGreaterEqual(FRONTIER_MIN_WITNESSES, 2)
        self.assertGreaterEqual(CANONICAL_MIN_WITNESSES, 2)


if __name__ == "__main__":
    unittest.main()
