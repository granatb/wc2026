"""Pins the engine's EXACT simulated output for a fixed seed.

Why this exists: every other test of `simulate_round` asserts directionally
(`assertGreater`) or with a tolerance (`delta=0.03`). None of them pin exact values,
so a change to the ORDER or NUMBER of `rng` draws inside the sim loop would shift
every projection while leaving the whole suite green — the distributions stay
statistically identical, only the specific draws move.

That matters because the published World Cup projections and the /track-record/
grading were produced by a specific RNG sequence. Silently changing it makes
regenerated numbers disagree with what was published.

This test was added after the FPL engine extensions (injectable priors, the four
additive PlayerSample fields, the per-match hook) were verified byte-identical
against the pre-change commit by direct comparison.

**When this test fails**, the engine's RNG consumption changed. That is not
automatically wrong — but it must be a DELIBERATE decision, not a side effect:

1. Confirm the change was intended.
2. Confirm World Cup priors are unaffected, or accept that WC numbers move.
3. Update EXPECTED_DIGEST below and note the reason in CHANGELOG.md.

Do not "fix" a failure here by loosening the assertion.

One non-engine cause to rule out first: the digest depends on `random.Random`'s
`random()` and `gauss()` output, which is stable within a CPython version but is not
guaranteed across major upgrades. Recorded under Python 3.9.6. If this test starts
failing immediately after a Python upgrade and nothing in `core/` changed, that is
the cause — re-record the digest and say so in the commit message.
"""

import hashlib
import unittest
from datetime import datetime, timezone
from unittest import mock

from core import engine_events, fixtures, ratings

# World-Cup-shaped priors: sot_per90 populated, defcon_per90 / saves_per90 left at
# their 0.0 defaults, exactly as core/ratings.py builds them. The FPL-only fields
# being zero is what keeps the FPL sampling branches from drawing any rng, which is
# why this digest is unchanged by the FPL port.
_SQUADS = {
    "Spain": [
        ratings.PlayerPrior("Pedri", "Spain", "MID", 0.92, 84, 0.18, 0.22, 1.1, False),
        ratings.PlayerPrior("Morata", "Spain", "FWD", 0.71, 70, 0.31, 0.09, 1.7, True),
        ratings.PlayerPrior("Simon", "Spain", "GK", 0.98, 90, 0.0, 0.0, 0.0, False),
        ratings.PlayerPrior("Cubarsi", "Spain", "DEF", 0.85, 88, 0.04, 0.05, 0.4, False),
    ],
    "Germany": [
        ratings.PlayerPrior("Musiala", "Germany", "MID", 0.88, 80, 0.21, 0.24, 1.2, False),
        ratings.PlayerPrior("Havertz", "Germany", "FWD", 0.64, 66, 0.27, 0.11, 1.5, False),
        ratings.PlayerPrior("Neuer", "Germany", "GK", 0.95, 90, 0.0, 0.0, 0.0, False),
    ],
}

EXPECTED_DIGEST = "9f892aed68afdbc46d69054237399306f738a62cb2bdc45509bc8582a984a5b1"


def _serialise(players: dict, matches: dict) -> str:
    lines = []
    for name in sorted(players):
        ps = players[name]
        lines.append(
            f"{name}|{ps.sims}|{ps.goals:.6f}|{ps.assists:.6f}|{ps.sot:.6f}|"
            f"{ps.minutes:.6f}|{ps.played:.0f}|{ps.clean_sheet:.0f}|"
            f"{ps.conc_beyond:.0f}|{ps.yellow:.0f}|{ps.red:.0f}|{ps.saves:.0f}|"
            f"{ps.motm:.0f}|{ps.decisive_win:.0f}|{ps.decisive_draw:.0f}")
    ms = matches["DETERM1"]
    lines.append("|".join(f"{k[0]}-{k[1]}:{v}" for k, v in sorted(ms.scorelines.items())))
    return "\n".join(lines)


class TestEngineDeterminism(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.Fixture(
            "DETERM1", "Spain", "Germany",
            kickoff=datetime(2026, 6, 20, 18, 0, tzinfo=timezone.utc),
            stage="R32", fantasy_round=777, neutral=True,
            lam_home=1.55, lam_away=1.25,
        )
        fixtures.SCHEDULE.append(self.fx)
        self.addCleanup(lambda: fixtures.SCHEDULE.remove(self.fx))

    def _run(self):
        with mock.patch.object(ratings, "players_for_team",
                               side_effect=lambda t: _SQUADS.get(t, [])):
            return engine_events.simulate_round(777, sims=4000, seed=12345)

    def test_exact_output_matches_the_recorded_digest(self):
        payload = _serialise(*self._run())
        digest = hashlib.sha256(payload.encode()).hexdigest()
        self.assertEqual(
            digest, EXPECTED_DIGEST,
            "\n\nThe engine's exact simulated output changed. See this module's "
            "docstring before touching EXPECTED_DIGEST.\n\nActual payload:\n"
            + payload)

    def test_same_seed_is_reproducible_within_a_process(self):
        self.assertEqual(_serialise(*self._run()), _serialise(*self._run()))

    def test_wc_shaped_priors_draw_no_fpl_rng(self):
        """The FPL sampling branches must not consume rng for WC priors.

        defcon_samples is appended only when defcon_per90 > 0. If that guard were
        removed, every WC projection would shift — this asserts the guard holds.
        """
        players, _ = self._run()
        self.assertTrue(all(not p.defcon_samples for p in players.values()))
        self.assertEqual(
            [n for n, p in players.items() if p.save_samples],
            [n for n, p in players.items() if p.position == "GK"])
