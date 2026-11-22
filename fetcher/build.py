#!/usr/bin/env python3
"""Baut data/events.json: Seeds + Fußball-API -> Senderegeln -> Overrides -> Zeitfenster.

Aufruf (aus dem Repo-Root):  python fetcher/build.py
Umgebungsvariablen:  API_FOOTBALL_KEY (optional), WINDOW_DAYS (Standard 14)
"""
from __future__ import annotations

import json
import os
import sys
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from providers import api_football  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "data" / "events.json"
TZ = ZoneInfo("Europe/Warsaw")
WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "14"))


# ---------- Helfer ----------

def slug(text: str) -> str:
    text = (text or "").lower().replace("ł", "l")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "-".join("".join(c if c.isalnum() else " " for c in text).split())


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parse_time(value) -> time | None:
    if not value:
        return None
    if isinstance(value, time):
        return value
    h, m = str(value).split(":")[:2]
    return time(int(h), int(m))


# ---------- Quellen ----------

COUNTRY_PL = {
    "NO": "Norwegia", "FI": "Finlandia", "PL": "Polska", "DE": "Niemcy", "CH": "Szwajcaria",
    "AT": "Austria", "JP": "Japonia", "US": "USA", "SE": "Szwecja", "SI": "Słowenia",
    "ES": "Hiszpania", "TH": "Tajlandia", "QA": "Katar", "AR": "Argentyna", "FR": "Francja",
    "IT": "Włochy", "NL": "Holandia", "CZ": "Czechy", "GB": "Wielka Brytania", "AU": "Australia",
}


def events_from_seed(path: Path) -> list[dict]:
    data = load_yaml(path)
    defaults = data.get("defaults", {})
    out = []
    for raw in data.get("events", []):
        e = {**defaults, **raw}
        city, kind = e.get("city"), e.get("kind")
        e.setdefault("title", " — ".join(p for p in (city, kind) if p) or e.get("home", ""))
        if e.get("home") and e.get("away"):
            e["title"] = f"{e['home']} – {e['away']}"
        e["time"] = parse_time(e.get("time"))
        e.setdefault("venue", COUNTRY_PL.get(e.get("country")))
        e["source"] = "seed"
        out.append(e)
    return out


# ---------- Verarbeitung ----------

def apply_rules(ev: dict, rules_cfg: dict) -> None:
    """Setzt channels/online anhand rules.yml, sofern der Termin nicht schon Sender mitbringt."""
    explicit = ev.get("channels")
    channels, online = list(explicit or []), []
    matched_primary = bool(explicit)
    for rule in rules_cfg.get("rules", []):
        if not all(ev.get(k, False if k == "poland" else None) == v for k, v in rule["match"].items()):
            continue
        if "channels" in rule and not matched_primary:
            channels, online = list(rule["channels"]), list(rule.get("online", []))
            matched_primary = True
        elif "channels" in rule and matched_primary and not online:
            online = list(rule.get("online", []))
        for extra in rule.get("add_channels", []):
            if extra not in channels:
                channels.append(extra)
    ev["channels"], ev["online"] = channels, online
    if not channels:
        ev["note"] = rules_cfg.get("fallback", {}).get("note", "Sprawdź program TV")


def finalize(ev: dict) -> dict:
    d: date = ev["date"]
    t: time | None = ev.get("time")
    return {
        "id": ev["id"],
        "sport": ev["sport"],
        "competition": ev.get("competition"),
        "title": ev["title"],
        "date": d.isoformat(),
        "start": datetime.combine(d, t, TZ).isoformat() if t else None,
        "venue": ev.get("venue"),
        "country": ev.get("country"),
        "poland": bool(ev.get("poland", False)),
        "channels": ev["channels"],
        "online": ev["online"],
        "note": ev.get("note"),
        **({"stale": True} if ev.get("stale") else {}),
    }


def assign_ids(events: list[dict]) -> None:
    seen: dict[str, int] = {}
    for ev in sorted(events, key=lambda e: (e["date"], e.get("time") or time(0, 0))):
        base = f"{ev['sport']}-{ev['date'].isoformat()}-{slug(ev.get('city') or ev['title'])}"
        seen[base] = seen.get(base, 0) + 1
        ev["id"] = base if seen[base] == 1 else f"{base}-{slug(ev.get('kind') or str(seen[base]))}"


def apply_overrides(events: list[dict], overrides: list[dict]) -> list[dict]:
    by_id = {o["id"]: o for o in overrides or []}
    result = []
    for ev in events:
        o = by_id.get(ev["id"])
        if o:
            if o.get("hide"):
                continue
            for k, v in o.items():
                if k in ("id", "hide"):
                    continue
                ev[k] = parse_time(v) if k == "time" else v
        result.append(ev)
    return result


def carry_over_stale(previous: dict, start: date, end: date) -> list[dict]:
    """Fällt die Fußball-API aus, behalten wir gestrige API-Termine (markiert als 'stale')."""
    kept = []
    for p in previous.get("events", []):
        if p.get("sport") != "pilka" or not (start.isoformat() <= p["date"] <= end.isoformat()):
            continue
        t = parse_time(p["start"][11:16]) if p.get("start") else None
        kept.append({
            **p, "date": date.fromisoformat(p["date"]), "time": t, "stale": True,
            "source": "carried", "city": None,
        })
    return kept


# ---------- Hauptprogramm ----------

def build(today: date | None = None, previous_path: Path = OUT) -> dict:
    today = today or datetime.now(TZ).date()
    start, end = today, today + timedelta(days=WINDOW_DAYS)

    rules_cfg = load_yaml(ROOT / "config" / "rules.yml")
    overrides = load_yaml(ROOT / "config" / "overrides.yml").get("overrides", [])

    events: list[dict] = []
    status: dict[str, str] = {}

    for seed in sorted((ROOT / "seeds").glob("*.yml")):
        items = events_from_seed(seed)
        events += items
        status[f"seed:{seed.stem}"] = f"ok ({len(items)})"

    try:
        api_events = api_football.fetch(start, end, ROOT / "config" / "football.yml")
        events += api_events
        status["api_football"] = f"ok ({len(api_events)})"
    except LookupError as e:  # kein Key -> bewusst übersprungen
        status["api_football"] = f"übersprungen: {e}"
    except Exception as e:  # noqa: BLE001  Netz/API kaputt -> alte Daten behalten
        status["api_football"] = f"FEHLER: {e}"
        print(f"[WARN] api_football: {e}", file=sys.stderr)
        if previous_path.exists():
            prev = json.loads(previous_path.read_text(encoding="utf-8"))
            events += carry_over_stale(prev, start, end)

    # Zeitfenster
    events = [e for e in events if start <= e["date"] <= end]
    assign_ids(events)
    events = apply_overrides(events, overrides)
    for ev in events:
        apply_rules(ev, rules_cfg)  # explizit gesetzte channels (Seed/Override) bleiben erhalten

    events.sort(key=lambda e: (e["date"], e.get("time") or time(23, 59), e["title"]))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "timezone": "Europe/Warsaw",
        "window_days": WINDOW_DAYS,
        "sources": status,
        "events": [finalize(e) for e in events],
    }


def main() -> None:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(result['events'])} Termine -> {OUT}")
    for k, v in result["sources"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
