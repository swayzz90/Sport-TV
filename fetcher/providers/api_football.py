"""Fußball-Termine über API-Football (https://www.api-football.com, v3).

Benötigt den Secret/ENV-Wert API_FOOTBALL_KEY (Gratis-Tarif: 100 Abfragen/Tag; wir brauchen ~11).
Liefert nur Männer-A-Nationalmannschaften:
  * alle Spiele Polens (Team-ID aus config/football.yml)
  * alle Spiele der in config/football.yml markierten Turniere (MŚ, ME, Liga Narodów ...)

HINWEIS: Dieses Modul wurde ohne Live-Zugriff geschrieben (Sandbox ohne Internet) und gegen
Beispieldaten im dokumentierten Antwortformat getestet. Beim ersten Action-Lauf Log prüfen.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests
import yaml

BASE = "https://v3.football.api-sports.io"
TZ = ZoneInfo("Europe/Warsaw")

# Nur das Nötigste ins Polnische übersetzen; unbekannte Namen bleiben englisch.
COUNTRY_PL = {
    "Poland": "Polska", "Germany": "Niemcy", "France": "Francja", "Spain": "Hiszpania",
    "Italy": "Włochy", "England": "Anglia", "Portugal": "Portugalia", "Netherlands": "Holandia",
    "Belgium": "Belgia", "Croatia": "Chorwacja", "Sweden": "Szwecja", "Romania": "Rumunia",
    "Bosnia and Herzegovina": "Bośnia i Hercegowina", "Bosnia & Herzegovina": "Bośnia i Hercegowina",
    "Ukraine": "Ukraina", "Czech Republic": "Czechy", "Czechia": "Czechy", "Slovakia": "Słowacja",
    "Austria": "Austria", "Switzerland": "Szwajcaria", "Denmark": "Dania", "Norway": "Norwegia",
    "Finland": "Finlandia", "Lithuania": "Litwa", "Malta": "Malta", "Albania": "Albania",
    "Hungary": "Węgry", "Scotland": "Szkocja", "Wales": "Walia", "Turkey": "Turcja",
    "Serbia": "Serbia", "Greece": "Grecja", "Ireland": "Irlandia", "Moldova": "Mołdawia",
    "Brazil": "Brazylia", "Argentina": "Argentyna", "USA": "USA", "Mexico": "Meksyk",
    "Nigeria": "Nigeria", "Japan": "Japonia", "Morocco": "Maroko",
}

# Wettbewerbe, bei denen API-Football Frauen-/Jugendteams mit Suffix liefert -> aussortieren.
_NOT_MEN_SENIOR = re.compile(r"\b(W|U\s?\d{2})$")

_SKIP_STATUS = {"CANC", "ABD", "AWD", "WO", "PST"}


def _pl(name: str) -> str:
    return COUNTRY_PL.get(name, name)


def parse_fixture(item: dict, cfg: dict) -> dict | None:
    """Wandelt einen API-Football-Eintrag in unser Event-Format. None = überspringen."""
    fx, lg, tm = item["fixture"], item["league"], item["teams"]
    status = (fx.get("status") or {}).get("short", "")
    if status in _SKIP_STATUS:
        return None

    home, away = tm["home"], tm["away"]
    if _NOT_MEN_SENIOR.search(home["name"]) or _NOT_MEN_SENIOR.search(away["name"]):
        return None

    poland_id = cfg["poland_team_id"]
    is_poland = poland_id in (home.get("id"), away.get("id"))

    league_cfg = next((l for l in cfg["leagues"] if l["id"] == lg["id"]), None)
    if not is_poland and not (league_cfg and league_cfg.get("all_matches")):
        return None

    start = datetime.fromisoformat(fx["date"]).astimezone(TZ)
    time_known = status != "TBD"

    venue = fx.get("venue") or {}
    venue_txt = ", ".join(p for p in (venue.get("name"), venue.get("city")) if p) or None

    return {
        "sport": "pilka",
        "competition": (league_cfg or {}).get("name") or lg.get("name"),
        "competition_key": (league_cfg or {}).get("key"),
        "title": f"{_pl(home['name'])} – {_pl(away['name'])}",
        "date": start.date(),
        "time": start.time().replace(second=0, microsecond=0) if time_known else None,
        "venue": venue_txt,
        "poland": is_poland,
        "source": "api",
        "api_id": fx["id"],
    }


def _get(path: str, params: dict, key: str) -> list[dict]:
    r = requests.get(f"{BASE}{path}", params=params, headers={"x-apisports-key": key}, timeout=30)
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(f"API-Football: {body['errors']}")
    return body.get("response", [])


def fetch(start: date, end: date, config_path) -> list[dict]:
    key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not key:
        raise LookupError("kein API_FOOTBALL_KEY gesetzt")

    cfg = yaml.safe_load(open(config_path, encoding="utf-8"))
    rng = {"from": start.isoformat(), "to": end.isoformat(), "timezone": "Europe/Warsaw"}

    raw: list[dict] = []
    raw += _get("/fixtures", {"team": cfg["poland_team_id"], **rng}, key)

    seasons = sorted({start.year - 1, start.year, end.year})
    for league in cfg["leagues"]:
        if not league.get("all_matches"):
            continue
        for season in seasons:
            raw += _get("/fixtures", {"league": league["id"], "season": season, **rng}, key)

    events, seen = [], set()
    for item in raw:
        fid = item["fixture"]["id"]
        if fid in seen:
            continue
        seen.add(fid)
        ev = parse_fixture(item, cfg)
        if ev:
            events.append(ev)
    return events
