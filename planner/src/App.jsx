import { useState, useEffect } from "react";

const C = {
  ground: "#0B1026",
  panel: "#151C40",
  panelHi: "#1E2757",
  line: "#2C3670",
  cyan: "#38D6E8",
  yellow: "#F5C518",
  green: "#35D07F",
  red: "#FF4D6D",
  text: "#E6E9F5",
  dim: "#8B93BD",
};

const MONO = 'ui-monospace, "SF Mono", Menlo, Consolas, monospace';
const SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

const POS = ["GK", "DEF", "MID", "FWD"];
const LIMITS = { GK: 2, DEF: 5, MID: 5, FWD: 3 };

const SEED_SQUAD = [
  { id: 1, name: "Kinsky", pos: "GK", club: "TOT", price: 4.5 },
  { id: 2, name: "Dúbravka", pos: "GK", club: "TOT", price: 4.0 },
  { id: 3, name: "Ben White", pos: "DEF", club: "ARS", price: 5.5 },
  { id: 4, name: "Maguire", pos: "DEF", club: "MUN", price: 5.0 },
  { id: 5, name: "Ballard", pos: "DEF", club: "SUN", price: 5.0 },
  { id: 6, name: "De Cuyper", pos: "DEF", club: "BHA", price: 4.5 },
  { id: 7, name: "O'Shea", pos: "DEF", club: "IPS", price: 4.0 },
  { id: 8, name: "Bruno Fernandes", pos: "MID", club: "MUN", price: 12.0 },
  { id: 9, name: "Mbeumo", pos: "MID", club: "BRE", price: 8.0 },
  { id: 10, name: "Tzolis", pos: "MID", club: "BRU", price: 6.5 },
  { id: 11, name: "Ødegaard", pos: "MID", club: "ARS", price: 6.5 },
  { id: 12, name: "D. Gómez", pos: "MID", club: "BHA", price: 5.0 },
  { id: 13, name: "Haaland", pos: "FWD", club: "MCI", price: 15.5 },
  { id: 14, name: "João Pedro", pos: "FWD", club: "BHA", price: 7.5 },
  { id: 15, name: "Calvert-Lewin", pos: "FWD", club: "LEE", price: 6.0 },
];

const blankGW = () => ({ moves: [], captain: "", chip: "", note: "" });
const SEED_PLAN = [blankGW(), blankGW(), blankGW(), blankGW(), blankGW()];

const KEY = "fpl:planner:v2";

function load() {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function save(data) {
  try {
    localStorage.setItem(KEY, JSON.stringify(data));
    return true;
  } catch {
    return false;
  }
}

function mode(behind, left) {
  if (left <= 0) return { label: "SEASON OVER", color: C.dim, gloss: "No gameweeks left." };
  if (behind < 0) return { label: "SHIELD", color: C.cyan, gloss: "You lead. Mirror the chasers, match their captain, avoid unique picks." };
  const p = behind / left;
  if (p <= 0.5) return { label: "SAFE", color: C.green, gloss: "Template core, template captain, no hits. Grind it down on transfers." };
  if (p <= 1.5) return { label: "BALANCED", color: C.yellow, gloss: "One calculated differential. Template captain unless the gap is tiny." };
  if (p <= 3) return { label: "AGGRESSIVE", color: "#FF9F45", gloss: "Two or three sub-10% picks. Off-template captain when xPts are close." };
  return { label: "SWING", color: C.red, gloss: "Contrarian captain, low ownership, chips on max-variance weeks." };
}

export default function App() {
  const [squad, setSquad] = useState(SEED_SQUAD);
  const [bank, setBank] = useState(0.5);
  const [startGW, setStartGW] = useState(1);
  const [startFT, setStartFT] = useState(1);
  const [plan, setPlan] = useState(SEED_PLAN);
  const [behind, setBehind] = useState(0);
  const [left, setLeft] = useState(38);
  const [showSquad, setShowSquad] = useState(false);
  const [status, setStatus] = useState("Loading your plan\u2026");
  const [ready, setReady] = useState(false);
  const [exportText, setExportText] = useState("");

  useEffect(() => {
    const d = load();
    if (d) {
      setSquad(d.squad); setBank(d.bank); setStartGW(d.startGW);
      setStartFT(d.startFT); setPlan(d.plan);
      setBehind(d.behind ?? 0); setLeft(d.left ?? 38);
      setStatus("Plan loaded");
    } else {
      setStatus("New plan \u2014 seeded with your GW1 squad");
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    const t = setTimeout(() => {
      const ok = save({ squad, bank, startGW, startFT, plan, behind, left });
      setStatus(ok ? "Saved" : "Couldn\u2019t save \u2014 changes stay for this session only");
    }, 600);
    return () => clearTimeout(t);
  }, [squad, bank, startGW, startFT, plan, behind, left, ready]);

  const steps = [];
  let cur = squad.map((p) => ({ ...p }));
  let money = Number(bank) || 0;
  let ft = Number(startFT) || 0;
  let totalHits = 0;

  plan.forEach((gw, i) => {
    const avail = Math.min(5, ft);
    const used = gw.moves.length;
    const hits = Math.max(0, used - avail);
    totalHits += hits;

    const errs = [];
    gw.moves.forEach((m) => {
      const idx = cur.findIndex((p) => p.id === m.outId);
      if (idx === -1) { errs.push(`${m.outName || "A player"} isn't in the squad at this point`); return; }
      const out = cur[idx];
      const price = Number(m.inPrice) || 0;
      money += out.price - price;
      cur[idx] = { id: `n${i}-${idx}-${m.inName}`, name: m.inName || "?", pos: m.inPos || out.pos, club: (m.inClub || "").toUpperCase(), price };
      if (m.inPos && m.inPos !== out.pos) errs.push(`${m.inName || "New player"} is a ${m.inPos} but replaces a ${out.pos}`);
    });

    if (money < -0.001) errs.push(`Over budget by \u00a3${Math.abs(money).toFixed(1)}m`);
    const clubs = {};
    cur.forEach((p) => { if (p.club) clubs[p.club] = (clubs[p.club] || 0) + 1; });
    Object.entries(clubs).forEach(([c, n]) => { if (n > 3) errs.push(`${n} players from ${c} \u2014 max is 3`); });
    POS.forEach((p) => {
      const n = cur.filter((x) => x.pos === p).length;
      if (n !== LIMITS[p]) errs.push(`${n} ${p} \u2014 need ${LIMITS[p]}`);
    });

    steps.push({ gw: Number(startGW) + i, avail, used, hits, money, errs, snapshot: cur.map((p) => ({ ...p })) });
    ft = Math.min(5, avail - Math.min(used, avail) + 1);
  });

  const setGW = (i, patch) => setPlan(plan.map((g, j) => (j === i ? { ...g, ...patch } : g)));

  const addMove = (i) => {
    const first = squad[0];
    setGW(i, { moves: [...plan[i].moves, { outId: first.id, outName: first.name, inName: "", inPos: first.pos, inClub: "", inPrice: first.price }] });
  };

  const setMove = (i, k, patch) =>
    setGW(i, { moves: plan[i].moves.map((m, j) => (j === k ? { ...m, ...patch } : m)) });

  const dropMove = (i, k) => setGW(i, { moves: plan[i].moves.filter((_, j) => j !== k) });

  const md = mode(Number(behind), Number(left));

  const buildExport = () => {
    const L = [];
    L.push(`FPL PLAN \u2014 GW${startGW}\u2013GW${Number(startGW) + 4}`);
    L.push(`Mode: ${md.label} (${behind} behind, ${left} GWs left)`);
    L.push(`Bank \u00a3${Number(bank).toFixed(1)}m \u00b7 Free transfers ${startFT} \u00b7 Hits planned ${totalHits} (${totalHits * -4} pts)`);
    L.push("");
    L.push("SQUAD NOW");
    POS.forEach((p) => {
      const l = squad.filter((x) => x.pos === p).map((x) => `${x.name} (${x.club}) \u00a3${x.price.toFixed(1)}`).join(" \u00b7 ");
      L.push(`${p}: ${l}`);
    });
    L.push("");
    plan.forEach((g, i) => {
      const s = steps[i];
      L.push(`GW${s.gw} \u2014 FT ${s.avail}, using ${s.used}${s.hits ? `, ${s.hits} hit(s)` : ""}, bank after \u00a3${s.money.toFixed(1)}m`);
      if (g.moves.length) g.moves.forEach((m) => L.push(`  OUT ${m.outName} \u2192 IN ${m.inName || "?"} (${m.inClub || "?"}) \u00a3${Number(m.inPrice || 0).toFixed(1)}`));
      else L.push("  No transfers \u2014 rolling");
      if (g.captain) L.push(`  Captain: ${g.captain}`);
      if (g.chip) L.push(`  Chip: ${g.chip}`);
      if (g.note) L.push(`  Note: ${g.note}`);
      if (s.errs.length) L.push(`  \u26a0 ${s.errs.join("; ")}`);
    });
    setExportText(L.join("\n"));
  };

  const reset = () => {
    setSquad(SEED_SQUAD); setBank(0.5); setStartGW(1); setStartFT(1);
    setPlan(SEED_PLAN.map(blankGW)); setBehind(0); setLeft(38); setExportText("");
  };

  const inp = { background: C.ground, color: C.text, border: `1px solid ${C.line}`, borderRadius: 6, padding: "7px 9px", fontFamily: MONO, fontSize: 13, width: "100%", boxSizing: "border-box" };
  const lbl = { fontFamily: MONO, fontSize: 10, letterSpacing: "0.12em", color: C.dim, textTransform: "uppercase", display: "block", marginBottom: 4 };
  const btn = { background: C.panelHi, color: C.cyan, border: `1px solid ${C.line}`, borderRadius: 6, padding: "9px 14px", fontFamily: MONO, fontSize: 12, letterSpacing: "0.08em", cursor: "pointer" };

  return (
    <div style={{ background: C.ground, color: C.text, fontFamily: SANS, minHeight: "100vh", padding: "16px 12px 48px" }}>
      <style>{`
        *{margin:0;box-sizing:border-box}
        input,select,textarea{outline:none}
        input:focus,select:focus,textarea:focus{border-color:${C.cyan}!important;box-shadow:0 0 0 2px rgba(56,214,232,.25)}
        button:focus-visible{outline:2px solid ${C.cyan};outline-offset:2px}
        @media (prefers-reduced-motion:no-preference){.gwcard{transition:border-color .2s}}
      `}</style>

      <div style={{ maxWidth: 620, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, borderBottom: `2px solid ${C.cyan}`, paddingBottom: 8, marginBottom: 4 }}>
          <span style={{ fontFamily: MONO, fontSize: 11, color: C.ground, background: C.cyan, padding: "2px 7px", borderRadius: 3, fontWeight: 700 }}>P302</span>
          <h1 style={{ fontFamily: MONO, fontSize: 17, letterSpacing: "0.16em", margin: 0, color: C.yellow, fontWeight: 700 }}>FPLD PLANNER</h1>
        </div>
        <div style={{ fontFamily: MONO, fontSize: 10, color: C.dim, marginBottom: 18, letterSpacing: "0.08em" }}>{status.toUpperCase()}</div>

        <section style={{ background: C.panel, border: `1px solid ${C.line}`, borderLeft: `3px solid ${md.color}`, borderRadius: 8, padding: 14, marginBottom: 16 }}>
          <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
            <div style={{ flex: 1 }}>
              <label style={lbl}>Points behind leader</label>
              <input style={inp} type="number" value={behind} onChange={(e) => setBehind(e.target.value)} />
            </div>
            <div style={{ flex: 1 }}>
              <label style={lbl}>Gameweeks left</label>
              <input style={inp} type="number" value={left} onChange={(e) => setLeft(e.target.value)} />
            </div>
          </div>
          <div style={{ fontFamily: MONO, fontSize: 22, letterSpacing: "0.1em", color: md.color, fontWeight: 700 }}>{md.label}</div>
          <div style={{ fontSize: 13, color: C.dim, marginTop: 4, lineHeight: 1.45 }}>{md.gloss}</div>
        </section>

        <section style={{ display: "flex", gap: 8, marginBottom: 16 }}>
          {[["First GW", startGW, setStartGW], ["Bank \u00a3m", bank, setBank], ["Free transfers", startFT, setStartFT]].map(([l, v, s]) => (
            <div key={l} style={{ flex: 1 }}>
              <label style={lbl}>{l}</label>
              <input style={inp} type="number" step="0.1" value={v} onChange={(e) => s(e.target.value)} />
            </div>
          ))}
        </section>

        <button style={{ ...btn, width: "100%", marginBottom: showSquad ? 10 : 20, textAlign: "left" }} onClick={() => setShowSquad(!showSquad)}>
          {showSquad ? "\u25be" : "\u25b8"} SQUAD ({squad.length}) {"\u2014"} {"\u00a3"}{squad.reduce((a, p) => a + p.price, 0).toFixed(1)}m
        </button>
        {showSquad && (
          <div style={{ marginBottom: 20 }}>
            {POS.map((p) => (
              <div key={p} style={{ marginBottom: 10 }}>
                <div style={{ ...lbl, color: C.cyan, marginBottom: 6 }}>{p}</div>
                {squad.filter((x) => x.pos === p).map((pl) => (
                  <div key={pl.id} style={{ display: "flex", gap: 6, marginBottom: 5 }}>
                    <input style={{ ...inp, flex: 3 }} value={pl.name} onChange={(e) => setSquad(squad.map((s) => s.id === pl.id ? { ...s, name: e.target.value } : s))} />
                    <input style={{ ...inp, flex: 1, textTransform: "uppercase" }} value={pl.club} onChange={(e) => setSquad(squad.map((s) => s.id === pl.id ? { ...s, club: e.target.value.toUpperCase() } : s))} />
                    <input style={{ ...inp, flex: 1 }} type="number" step="0.1" value={pl.price} onChange={(e) => setSquad(squad.map((s) => s.id === pl.id ? { ...s, price: parseFloat(e.target.value) || 0 } : s))} />
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}

        {plan.map((g, i) => {
          const s = steps[i];
          const bad = s.errs.length > 0;
          return (
            <section key={i} className="gwcard" style={{ background: C.panel, border: `1px solid ${bad ? C.red : C.line}`, borderRadius: 8, padding: 14, marginBottom: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
                <span style={{ fontFamily: MONO, fontSize: 15, color: C.yellow, letterSpacing: "0.1em", fontWeight: 700 }}>GW{s.gw}</span>
                <span style={{ fontFamily: MONO, fontSize: 11, color: C.dim }}>
                  FT <b style={{ color: C.text }}>{s.avail}</b> {"\u00b7"} USING <b style={{ color: C.text }}>{s.used}</b>
                  {s.hits > 0 && <b style={{ color: C.red }}> {"\u00b7"} {s.hits * -4}PTS</b>}
                  {" \u00b7 \u00a3"}<b style={{ color: s.money < 0 ? C.red : C.green }}>{s.money.toFixed(1)}</b>m
                </span>
              </div>

              {g.moves.map((m, k) => (
                <div key={k} style={{ background: C.ground, border: `1px solid ${C.line}`, borderRadius: 6, padding: 9, marginBottom: 8 }}>
                  <label style={lbl}>Out</label>
                  <select style={{ ...inp, marginBottom: 8 }} value={m.outId}
                    onChange={(e) => {
                      const p = s.snapshot.find((x) => String(x.id) === e.target.value) || squad.find((x) => String(x.id) === e.target.value);
                      setMove(i, k, { outId: p ? p.id : e.target.value, outName: p ? p.name : "", inPos: m.inPos || (p ? p.pos : "") });
                    }}>
                    {s.snapshot.map((p) => <option key={p.id} value={p.id}>{p.pos} {"\u00b7"} {p.name} ({p.club}) {"\u00a3"}{p.price.toFixed(1)}</option>)}
                  </select>
                  <label style={lbl}>In</label>
                  <div style={{ display: "flex", gap: 6 }}>
                    <input style={{ ...inp, flex: 3 }} placeholder="Name" value={m.inName} onChange={(e) => setMove(i, k, { inName: e.target.value })} />
                    <input style={{ ...inp, flex: 1, textTransform: "uppercase" }} placeholder="CLUB" value={m.inClub} onChange={(e) => setMove(i, k, { inClub: e.target.value.toUpperCase() })} />
                    <input style={{ ...inp, flex: 1 }} type="number" step="0.1" placeholder={"\u00a3"} value={m.inPrice} onChange={(e) => setMove(i, k, { inPrice: e.target.value })} />
                  </div>
                  <button style={{ ...btn, color: C.red, padding: "5px 10px", marginTop: 8, fontSize: 10 }} onClick={() => dropMove(i, k)}>REMOVE</button>
                </div>
              ))}

              <button style={{ ...btn, width: "100%", marginBottom: 10 }} onClick={() => addMove(i)}>+ ADD TRANSFER</button>

              <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
                <div style={{ flex: 2 }}>
                  <label style={lbl}>Captain</label>
                  <select style={inp} value={g.captain} onChange={(e) => setGW(i, { captain: e.target.value })}>
                    <option value="">{"\u2014"}</option>
                    {s.snapshot.map((p) => <option key={p.id} value={p.name}>{p.name}</option>)}
                  </select>
                </div>
                <div style={{ flex: 2 }}>
                  <label style={lbl}>Chip</label>
                  <select style={inp} value={g.chip} onChange={(e) => setGW(i, { chip: e.target.value })}>
                    <option value="">{"\u2014"}</option>
                    {["Wildcard", "Free Hit", "Bench Boost", "Triple Captain"].map((c) => <option key={c}>{c}</option>)}
                  </select>
                </div>
              </div>
              <input style={inp} placeholder="Why this week?" value={g.note} onChange={(e) => setGW(i, { note: e.target.value })} />

              {bad && (
                <div style={{ marginTop: 10, borderTop: `1px solid ${C.red}`, paddingTop: 8 }}>
                  {s.errs.map((e, j) => <div key={j} style={{ fontFamily: MONO, fontSize: 11, color: C.red, marginBottom: 3 }}>{"\u26a0"} {e}</div>)}
                </div>
              )}
            </section>
          );
        })}

        <div style={{ fontFamily: MONO, fontSize: 12, color: C.dim, textAlign: "right", margin: "16px 0" }}>
          PLANNED HITS: <b style={{ color: totalHits ? C.red : C.green }}>{totalHits * -4} PTS</b>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button style={{ ...btn, flex: 1, background: C.cyan, color: C.ground, fontWeight: 700 }} onClick={buildExport}>BUILD SUMMARY</button>
          <button style={{ ...btn, color: C.dim }} onClick={reset}>RESET</button>
        </div>

        {exportText && (
          <div style={{ marginTop: 14 }}>
            <label style={lbl}>Copy this into our chat before each deadline</label>
            <textarea readOnly value={exportText} style={{ ...inp, height: 260, fontSize: 11, lineHeight: 1.5 }} onFocus={(e) => e.target.select()} />
          </div>
        )}
      </div>
    </div>
  );
}
