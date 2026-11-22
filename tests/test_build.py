"""Tests:  python -m unittest discover -s tests -v   (aus dem Repo-Root)"""
import sys
import unittest
from datetime import date, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fetcher"))

import build  # noqa: E402
from providers import api_football  # noqa: E402

RULES = build.load_yaml(ROOT / "fetcher" / "config" / "rules.yml")
FB_CFG = build.load_yaml(ROOT / "fetcher" / "config" / "football.yml")


def fixture(home, away, league_id=5, league="UEFA Nations League", hid=1, aid=2, date_iso="2027-03-26T20:45:00+01:00", status="NS"):
    return {
        "fixture": {"id": hid * 1000 + aid, "date": date_iso, "status": {"short": status},
                    "venue": {"name": "PGE Narodowy", "city": "Warszawa"}},
        "league": {"id": league_id, "name": league},
        "teams": {"home": {"id": hid, "name": home}, "away": {"id": aid, "name": away}},
    }


class Rules(unittest.TestCase):
    def ev(self, **kw):
        return {"sport": "skoki", "date": date(2026, 12, 5), "title": "x", **kw}

    def test_poland_match_on_tvp(self):
        e = self.ev(sport="pilka", poland=True)
        build.apply_rules(e, RULES)
        self.assertEqual(e["channels"], ["TVP Sport", "TVP 1"])

    def test_ski_jumping_poland_adds_tvp(self):
        e = self.ev(country="PL")
        build.apply_rules(e, RULES)
        self.assertEqual(e["channels"], ["Eurosport 1", "TVN", "TVP"])

    def test_ski_jumping_abroad_no_tvp(self):
        e = self.ev(country="NO")
        build.apply_rules(e, RULES)
        self.assertEqual(e["channels"], ["Eurosport 1", "TVN"])

    def test_motogp(self):
        e = self.ev(sport="motogp")
        build.apply_rules(e, RULES)
        self.assertEqual(e["channels"], ["Polsat Sport Premium 2"])

    def test_unknown_gets_note_not_invented_channel(self):
        e = self.ev(sport="pilka", competition_key="euro")
        build.apply_rules(e, RULES)
        self.assertEqual(e["channels"], [])
        self.assertTrue(e["note"])

    def test_explicit_channels_kept(self):
        e = self.ev(sport="motogp", channels=["Super Polsat"])
        build.apply_rules(e, RULES)
        self.assertEqual(e["channels"], ["Super Polsat"])
        self.assertIn("polsatsport.pl", e["online"])


class ApiFootball(unittest.TestCase):
    def test_poland_fixture(self):
        ev = api_football.parse_fixture(fixture("Poland", "Romania", hid=24, aid=1), FB_CFG)
        self.assertTrue(ev["poland"])
        self.assertEqual(ev["title"], "Polska – Rumunia")
        self.assertEqual(ev["time"], time(20, 45))
        self.assertEqual(ev["venue"], "PGE Narodowy, Warszawa")

    def test_timezone_converted_to_warsaw(self):
        ev = api_football.parse_fixture(fixture("Poland", "Sweden", hid=24, aid=3, date_iso="2027-03-26T19:45:00+00:00"), FB_CFG)
        self.assertEqual(ev["time"], time(20, 45))

    def test_other_nations_league_match_included(self):
        ev = api_football.parse_fixture(fixture("Germany", "France", hid=25, aid=2), FB_CFG)
        self.assertFalse(ev["poland"])
        self.assertEqual(ev["competition_key"], "nations_league")

    def test_other_friendly_excluded(self):
        self.assertIsNone(api_football.parse_fixture(fixture("Germany", "France", league_id=10, league="Friendlies", hid=25), FB_CFG))

    def test_women_and_youth_excluded(self):
        self.assertIsNone(api_football.parse_fixture(fixture("Poland W", "Spain W", hid=24), FB_CFG))
        self.assertIsNone(api_football.parse_fixture(fixture("Poland U21", "Spain U21", hid=24), FB_CFG))

    def test_cancelled_excluded(self):
        self.assertIsNone(api_football.parse_fixture(fixture("Poland", "Romania", hid=24, status="CANC"), FB_CFG))

    def test_tbd_time_unknown(self):
        ev = api_football.parse_fixture(fixture("Poland", "Romania", hid=24, status="TBD"), FB_CFG)
        self.assertIsNone(ev["time"])


class Pipeline(unittest.TestCase):
    def test_window_and_overrides(self):
        r = build.build(today=date(2026, 11, 22), previous_path=Path("/nonexistent"))
        dates = [e["date"] for e in r["events"]]
        self.assertTrue(all("2026-11-22" <= d <= "2026-12-06" for d in dates))
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(len({e["id"] for e in r["events"]}), len(r["events"]))

    def test_overrides_hide_and_override_time(self):
        evs = [{"id": "a", "title": "A", "time": None}, {"id": "b", "title": "B", "time": None}]
        out = build.apply_overrides(evs, [{"id": "a", "hide": True}, {"id": "b", "time": "18:30"}])
        self.assertEqual([e["id"] for e in out], ["b"])
        self.assertEqual(out[0]["time"], time(18, 30))

    def test_duplicate_ids_get_suffix(self):
        evs = [
            {"sport": "skoki", "date": date(2027, 1, 23), "time": None, "city": "Sapporo", "title": "a", "kind": "mikst"},
            {"sport": "skoki", "date": date(2027, 1, 23), "time": None, "city": "Sapporo", "title": "b", "kind": "indywidualny"},
        ]
        build.assign_ids(evs)
        self.assertEqual(len({e["id"] for e in evs}), 2)

    def test_stale_carry_over_marks_events(self):
        prev = {"events": [{"id": "x", "sport": "pilka", "title": "Polska – X", "date": "2026-11-25",
                            "start": "2026-11-25T20:45:00+01:00", "channels": ["TVP Sport"], "online": [], "poland": True}]}
        kept = build.carry_over_stale(prev, date(2026, 11, 22), date(2026, 12, 6))
        self.assertTrue(kept[0]["stale"])
        self.assertEqual(kept[0]["time"], time(20, 45))


if __name__ == "__main__":
    unittest.main()
