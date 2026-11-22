"use strict";

const TZ = "Europe/Warsaw";
const SPORTS = {
  skoki: { label: "Skoki narciarskie", icon: "⛷️" },
  motogp: { label: "MotoGP", icon: "🏍️" },
  pilka: { label: "Piłka nożna", icon: "⚽" },
  igrzyska: { label: "Igrzyska", icon: "🏅" },
};
const LIVE_WINDOW_MS = 2.5 * 3600 * 1000; // wie lange ein Termin als "TERAZ" gilt
const STALE_AFTER_MS = 48 * 3600 * 1000;  // ab hier Warnbanner
const FILTER_KEY = "sporttv.filter";

const fmtDate = new Intl.DateTimeFormat("pl-PL", { timeZone: TZ, weekday: "long", day: "numeric", month: "long" });
const fmtTime = new Intl.DateTimeFormat("pl-PL", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const fmtStamp = new Intl.DateTimeFormat("pl-PL", { timeZone: TZ, day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const fmtISODay = new Intl.DateTimeFormat("en-CA", { timeZone: TZ }); // YYYY-MM-DD

let data = null;
let activeFilter = readFilter();

// ---------- kleine Helfer ----------

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function readFilter() {
  try { return localStorage.getItem(FILTER_KEY) || "all"; } catch { return "all"; }
}
function saveFilter(v) {
  try { localStorage.setItem(FILTER_KEY, v); } catch { /* optional */ }
}

function isoDay(date) { return fmtISODay.format(date); }

function dayLabel(dayStr) {
  const [y, m, d] = dayStr.split("-").map(Number);
  const noon = new Date(Date.UTC(y, m - 1, d, 12)); // Mittag UTC -> liegt in Warschau am selben Tag
  const text = fmtDate.format(noon);
  const today = isoDay(new Date());
  const tomorrow = isoDay(new Date(Date.now() + 86400000));
  const wrap = el("h2");
  if (dayStr === today) wrap.append(el("span", "today", "Dziś"), document.createTextNode(` · ${text}`));
  else if (dayStr === tomorrow) wrap.append(el("span", null, "Jutro"), document.createTextNode(` · ${text}`));
  else wrap.textContent = text;
  return wrap;
}

function brandClass(name) {
  const n = name.toLowerCase();
  if (n.startsWith("tvp")) return "tvp";
  if (n.includes("polsat")) return "polsat";
  if (n.includes("eurosport")) return "eurosport";
  if (n === "tvn") return "tvn";
  return "";
}

// ---------- Rendering ----------

function renderCard(ev, now) {
  const sport = SPORTS[ev.sport] || { label: ev.sport, icon: "📺" };
  const start = ev.start ? new Date(ev.start) : null;
  const age = start ? now - start.getTime() : null;
  const live = age !== null && age >= 0 && age <= LIVE_WINDOW_MS;
  const done = age !== null && age > LIVE_WINDOW_MS;

  const card = el("article", `card${ev.poland ? " poland" : ""}${done ? " done" : ""}`);
  card.dataset.sport = ev.sport;
  card.tabIndex = 0;

  const when = el("div", "when");
  if (start) {
    when.append(el("div", "time", fmtTime.format(start)));
    if (live) when.append(el("span", "live", "TERAZ"));
    else if (done) when.append(el("div", "time-note", "zakończone"));
  } else {
    when.append(el("div", "time unknown", "—:—"), el("div", "time-note", "godzina wkrótce"));
  }

  const body = el("div", "body");
  body.append(el("div", "title", ev.title));

  const meta = el("div", "meta");
  meta.append(el("span", "sport", `${sport.icon} ${ev.competition || sport.label}`));
  if (ev.venue) meta.append(document.createTextNode(` · ${ev.venue}`));
  body.append(meta);

  const channels = el("div", "channels");
  if (ev.channels && ev.channels.length) {
    for (const c of ev.channels) channels.append(el("span", `badge ${brandClass(c)}`, c));
  } else {
    channels.append(el("span", "badge none", ev.note || "Sprawdź program TV"));
  }
  body.append(channels);

  if (ev.online && ev.online.length && ev.channels && ev.channels.length) {
    body.append(el("div", "online", `Online: ${ev.online.join(", ")}`));
  }
  if (ev.stale) body.append(el("div", "stale-note", "Dane z poprzedniej aktualizacji — mogły się zmienić."));

  card.append(when, body);
  return card;
}

function renderFilters() {
  const nav = document.getElementById("filters");
  nav.replaceChildren();
  const present = new Set(data.events.map((e) => e.sport));
  const options = [["all", "Wszystko"], ...Object.entries(SPORTS).filter(([k]) => present.has(k)).map(([k, v]) => [k, v.label])];
  if (!options.some(([k]) => k === activeFilter)) activeFilter = "all";
  for (const [key, label] of options) {
    const b = el("button", "chip", label);
    b.type = "button";
    b.setAttribute("aria-pressed", String(key === activeFilter));
    b.addEventListener("click", () => { activeFilter = key; saveFilter(key); renderFilters(); renderList(); });
    nav.append(b);
  }
}

function renderList() {
  const list = document.getElementById("list");
  list.replaceChildren();
  const now = Date.now();
  const events = data.events.filter((e) => activeFilter === "all" || e.sport === activeFilter);

  if (!events.length) {
    list.append(el("div", "empty", "Brak transmisji w najbliższych dniach."));
    return;
  }

  const byDay = new Map();
  for (const e of events) {
    if (!byDay.has(e.date)) byDay.set(e.date, []);
    byDay.get(e.date).push(e);
  }
  for (const [day, items] of byDay) {
    const section = el("section", "day");
    section.append(dayLabel(day));
    for (const ev of items) section.append(renderCard(ev, now));
    list.append(section);
  }
}

function renderHeader() {
  const updated = document.getElementById("updated");
  const stale = document.getElementById("stale");
  const generated = new Date(data.generated_at);
  updated.textContent = `Zaktualizowano: ${fmtStamp.format(generated)}`;
  const tooOld = Date.now() - generated.getTime() > STALE_AFTER_MS;
  stale.hidden = !tooOld;
  if (tooOld) stale.textContent = "Dane mogą być nieaktualne — ostatnia aktualizacja była ponad 2 dni temu.";
}

function render() {
  renderHeader();
  renderFilters();
  renderList();
}

// ---------- Start ----------

async function load() {
  try {
    const res = await fetch("data/events.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(res.status);
    data = await res.json();
    render();
  } catch (err) {
    document.getElementById("updated").textContent = "";
    const list = document.getElementById("list");
    list.replaceChildren(el("div", "empty", "Nie udało się wczytać danych. Sprawdź połączenie z internetem i odśwież stronę."));
  }
}

load();
// "TERAZ"/"zakończone" aktuell halten; Daten nach Rückkehr in die App neu holen
setInterval(() => { if (data) renderList(); }, 60_000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => { /* optional */ });
}
