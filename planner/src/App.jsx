import { useState, useEffect } from "react";

/* ─── palette ─── */
const C = {
  bg: "#f8f9fa",
  card: "#ffffff",
  border: "#e2e6ea",
  accent: "#37003c",       // PL purple
  accentLight: "#f0e6f2",
  green: "#00ff87",        // PL green
  greenDark: "#02894e",
  cyan: "#04f5ff",
  red: "#e63946",
  yellow: "#f4a300",
  text: "#1a1a2e",
  dim: "#6c757d",
  badge: "#37003c",
};

const SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
const MONO = 'ui-monospace, "SF Mono", Menlo, Consolas, monospace';

const POS = ["GK", "DEF", "MID", "FWD"];
const LIMITS = { GK: 2, DEF: 5, MID: 5, FWD: 3 };
const POS_COLOR = { GK: "#f4a300", DEF: "#04f5ff", MID: "#00ff87", FWD: "#e63946" };

const FALLBACK_SQUAD = [
  { id: 1, name: "Kinsky", pos: "GK", club: "TOT", price: 4.5 },
  { id: 2, name: "Forster", pos: "GK", club: "BOU", price: 4.0 },
  { id: 3, name: "Gabriel", pos: "DEF", club: "ARS", price: 8.0 },
  { id: 4, name: "Shaw", pos: "DEF", club: "MUN", price: 4.5 },
  { id: 5, name: "Kayode", pos: "DEF", club: "BRE", price: 4.5 },
  { id: 6, name: "Thomas", pos: "DEF", club: "COV", price: 4.0 },
  { id: 7, name: "Egan", pos: "DEF", club: "HUL", price: 4.0 },
  { id: 8, name: "B.Fernandes", pos: "MID", club: "MUN", price: 12.0 },
  { id: 9, name: "Mbeumo", pos: "MID", club: "BRE", price: 8.0 },
  { id: 10, name: "Dewsbury-Hall", pos: "MID", club: "EVE", price: 6.5 },
  { id: 11, name: "\u00d8degaard", pos: "MID", club: "ARS", price: 6.5 },
  { id: 12, name: "Slater", pos: "MID", club: "HUL", price: 4.5 },
  { id: 13, name: "Haaland", pos: "FWD", club: "MCI", price: 15.5 },
  { id: 14, name: "Jo\u00e3o Pedro", pos: "FWD", club: "CHE", price: 7.5 },
  { id: 15, name: "Calvert-Lewin", pos: "FWD", club: "???", price: 6.0 },
];

const blankGW = () => ({ moves: [], captain: "", chip: "", note: "" });
const SEED_PLAN = [blankGW(), blankGW(), blankGW(), blankGW(), blankGW()];

const KEY = "fpl:planner:v2";

function load() {
  try { const raw = localStorage.getItem(KEY); return raw ? JSON.parse(raw) : null; }
  catch { return null; }
}
function save(data) {
  try { localStorage.setItem(KEY, JSON.stringify(data)); return true; }
  catch { return false; }
}

function modeCalc(behind, left) {
  if (left <= 0) return { label: "SEASON OVER", color: C.dim, gloss: "No gameweeks left." };
  if (behind < 0) return { label: "SHIELD", color: "#0077b6", gloss: "You lead. Mirror chasers, match their captain, avoid unique picks." };
  const p = behind / left;
  if (p <= 0.5) return { label: "SAFE", color: C.greenDark, gloss: "Template core, template captain, no hits." };
  if (p <= 1.5) return { label: "BALANCED", color: C.yellow, gloss: "One calculated differential. Template captain unless gap is tiny." };
  if (p <= 3) return { label: "AGGRESSIVE", color: "#e76f00", gloss: "Two or three sub-10% picks. Off-template captain when xPts close." };
  return { label: "SWING", color: C.red, gloss: "Contrarian captain, low ownership, chips on max-variance weeks." };
}

export default function App() {
  const [squad, setSquad] = useState(FALLBACK_SQUAD);
  const [bank, setBank] = useState(0.5);
  const [startGW, setStartGW] = useState(1);
  const [startFT, setStartFT] = useState(1);
  const [plan, setPlan] = useState(SEED_PLAN);
  const [behind, setBehind] = useState(0);
  const [left, setLeft] = useState(38);
  const [showSquad, setShowSquad] = useState(false);
  const [status, setStatus] = useState("Loading\u2026");
  const [ready, setReady] = useState(false);
  const [exportText, setExportText] = useState("");

  useEffect(() => {
    const d = load();
    if (d) {
      setSquad(d.squad); setBank(d.bank); setStartGW(d.startGW);
      setStartFT(d.startFT); setPlan(d.plan);
      setBehind(d.behind ?? 0); setLeft(d.left ?? 38);
      setStatus("Plan loaded");
      setReady(true);
    } else {
      fetch("./data/brief.json")
        .then(r => r.ok ? r.json() : null)
        .then(brief => {
          if (brief && brief.squad && brief.squad.length === 15) {
            const s = brief.squad.map(p => ({
              id: p.id, name: p.name, pos: p.pos,
              club: p.club, price: p.price,
              xpts: p.xpts_horizon ?? p.xpts ?? null,
            }));
            setSquad(s);
            setStartGW(brief.gw || 1);
            setBehind(brief.dial?.behind ?? 0);
            setLeft(brief.dial?.left ?? 38);
            setStatus(`Auto-populated from brief (${brief.date})`);
          } else {
            setStatus("New plan \u2014 using fallback squad");
          }
        })
        .catch(() => setStatus("New plan \u2014 using fallback squad"))
        .finally(() => setReady(true));
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    const t = setTimeout(() => {
      const ok = save({ squad, bank, startGW, startFT, plan, behind, left });
      setStatus(ok ? "Saved" : "Changes stay for this session only");
    }, 600);
    return () => clearTimeout(t);
  }, [squad, bank, startGW, startFT, plan, behind, left, ready]);

  /* ─── compute plan steps ─── */
  const steps = [];
  let cur = squad.map(p => ({ ...p }));
  let money = Number(bank) || 0;
  let ft = Number(startFT) || 0;
  let totalHits = 0;

  plan.forEach((gw, i) => {
    const avail = Math.min(5, ft);
    const used = gw.moves.length;
    const hits = Math.max(0, used - avail);
    totalHits += hits;
    const errs = [];
    gw.moves.forEach(m => {
      const idx = cur.findIndex(p => p.id === m.outId);
      if (idx === -1) { errs.push(`${m.outName || "?"} not in squad`); return; }
      const out = cur[idx];
      const price = Number(m.inPrice) || 0;
      money += out.price - price;
      cur[idx] = { id: `n${i}-${idx}-${m.inName}`, name: m.inName || "?", pos: m.inPos || out.pos, club: (m.inClub || "").toUpperCase(), price };
      if (m.inPos && m.inPos !== out.pos) errs.push(`${m.inName || "?"} is ${m.inPos}, replaces ${out.pos}`);
    });
    if (money < -0.001) errs.push(`Over budget by \u00a3${Math.abs(money).toFixed(1)}m`);
    const clubs = {};
    cur.forEach(p => { if (p.club) clubs[p.club] = (clubs[p.club] || 0) + 1; });
    Object.entries(clubs).forEach(([c, n]) => { if (n > 3) errs.push(`${n}\u00d7 ${c} (max 3)`); });
    POS.forEach(p => {
      const n = cur.filter(x => x.pos === p).length;
      if (n !== LIMITS[p]) errs.push(`${n} ${p}, need ${LIMITS[p]}`);
    });
    steps.push({ gw: Number(startGW) + i, avail, used, hits, money, errs, snapshot: cur.map(p => ({ ...p })) });
    ft = Math.min(5, avail - Math.min(used, avail) + 1);
  });

  const setGW = (i, patch) => setPlan(plan.map((g, j) => (j === i ? { ...g, ...patch } : g)));
  const addMove = i => {
    const first = squad[0];
    setGW(i, { moves: [...plan[i].moves, { outId: first.id, outName: first.name, inName: "", inPos: first.pos, inClub: "", inPrice: first.price }] });
  };
  const setMove = (i, k, patch) => setGW(i, { moves: plan[i].moves.map((m, j) => (j === k ? { ...m, ...patch } : m)) });
  const dropMove = (i, k) => setGW(i, { moves: plan[i].moves.filter((_, j) => j !== k) });
  const md = modeCalc(Number(behind), Number(left));

  const buildExport = () => {
    const L = [];
    L.push(`FPL PLAN \u2014 GW${startGW}\u2013GW${Number(startGW) + 4}`);
    L.push(`Mode: ${md.label} (${behind} behind, ${left} GWs left)`);
    L.push(`Bank \u00a3${Number(bank).toFixed(1)}m \u00b7 FTs ${startFT} \u00b7 Hits ${totalHits} (${totalHits * -4} pts)`);
    L.push("");
    L.push("SQUAD");
    POS.forEach(p => {
      const l = squad.filter(x => x.pos === p).map(x => `${x.name} (${x.club}) \u00a3${x.price.toFixed(1)}`).join(" \u00b7 ");
      L.push(`${p}: ${l}`);
    });
    L.push("");
    plan.forEach((g, i) => {
      const s = steps[i];
      L.push(`GW${s.gw} \u2014 FT ${s.avail}, using ${s.used}${s.hits ? `, ${s.hits} hit(s)` : ""}, bank \u00a3${s.money.toFixed(1)}m`);
      if (g.moves.length) g.moves.forEach(m => L.push(`  OUT ${m.outName} \u2192 IN ${m.inName || "?"} (${m.inClub || "?"}) \u00a3${Number(m.inPrice || 0).toFixed(1)}`));
      else L.push("  Roll FT");
      if (g.captain) L.push(`  Captain: ${g.captain}`);
      if (g.chip) L.push(`  Chip: ${g.chip}`);
      if (g.note) L.push(`  Note: ${g.note}`);
      if (s.errs.length) L.push(`  \u26a0 ${s.errs.join("; ")}`);
    });
    setExportText(L.join("\n"));
  };

  const reset = () => {
    setSquad(FALLBACK_SQUAD); setBank(0.5); setStartGW(1); setStartFT(1);
    setPlan(SEED_PLAN.map(blankGW)); setBehind(0); setLeft(38); setExportText("");
  };

  /* ─── styles ─── */
  const inp = {
    background: C.bg, color: C.text, border: `1px solid ${C.border}`,
    borderRadius: 8, padding: "8px 10px", fontFamily: SANS, fontSize: 14,
    width: "100%", boxSizing: "border-box",
  };
  const lbl = {
    fontFamily: SANS, fontSize: 11, fontWeight: 600, color: C.dim,
    textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 4,
  };
  const btn = {
    background: C.accent, color: "#fff", border: "none", borderRadius: 8,
    padding: "10px 16px", fontFamily: SANS, fontSize: 13, fontWeight: 600,
    cursor: "pointer",
  };
  const btnOutline = {
    ...btn, background: "transparent", color: C.accent,
    border: `1.5px solid ${C.accent}`,
  };

  return (
    <div style={{ background: C.bg, color: C.text, fontFamily: SANS, minHeight: "100vh", padding: "0 0 60px" }}>
      <style>{`
        *{margin:0;box-sizing:border-box}
        input,select,textarea{outline:none}
        input:focus,select:focus,textarea:focus{border-color:${C.accent}!important;box-shadow:0 0 0 3px ${C.accentLight}}
        button:hover{opacity:.9}
        button:active{transform:scale(.98)}
        ::selection{background:${C.accentLight}}
      `}</style>

      {/* header bar */}
      <div style={{ background: C.accent, padding: "14px 16px", marginBottom: 20 }}>
        <div style={{ maxWidth: 540, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 20, fontWeight: 800, color: C.green, letterSpacing: "-0.02em" }}>fpld</span>
            <span style={{ fontSize: 14, fontWeight: 500, color: "rgba(255,255,255,.7)" }}>planner</span>
          </div>
          <span style={{ fontSize: 11, color: "rgba(255,255,255,.5)", fontFamily: MONO }}>{status.toUpperCase()}</span>
        </div>
      </div>

      <div style={{ maxWidth: 540, margin: "0 auto", padding: "0 16px" }}>

        {/* risk dial */}
        <div style={{
          background: C.card, border: `1px solid ${C.border}`, borderRadius: 12,
          padding: 16, marginBottom: 16, borderLeft: `4px solid ${md.color}`,
          boxShadow: "0 1px 3px rgba(0,0,0,.06)",
        }}>
          <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
            <div style={{ flex: 1 }}>
              <label style={lbl}>Points behind</label>
              <input style={inp} type="number" value={behind} onChange={e => setBehind(e.target.value)} />
            </div>
            <div style={{ flex: 1 }}>
              <label style={lbl}>GWs left</label>
              <input style={inp} type="number" value={left} onChange={e => setLeft(e.target.value)} />
            </div>
          </div>
          <div style={{ fontSize: 20, fontWeight: 800, color: md.color, letterSpacing: "0.02em" }}>{md.label}</div>
          <div style={{ fontSize: 13, color: C.dim, marginTop: 4, lineHeight: 1.5 }}>{md.gloss}</div>
        </div>

        {/* settings row */}
        <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
          {[["First GW", startGW, setStartGW], ["Bank \u00a3m", bank, setBank], ["Free transfers", startFT, setStartFT]].map(([l, v, s]) => (
            <div key={l} style={{ flex: 1 }}>
              <label style={lbl}>{l}</label>
              <input style={inp} type="number" step="0.1" value={v} onChange={e => s(e.target.value)} />
            </div>
          ))}
        </div>

        {/* squad toggle */}
        <button
          style={{ ...btnOutline, width: "100%", marginBottom: 16, textAlign: "left", display: "flex", justifyContent: "space-between", alignItems: "center" }}
          onClick={() => setShowSquad(!showSquad)}
        >
          <span>{showSquad ? "\u25be" : "\u25b8"} Squad ({squad.length})</span>
          <span style={{ fontFamily: MONO, fontSize: 12, opacity: 0.7 }}>\u00a3{squad.reduce((a, p) => a + p.price, 0).toFixed(1)}m</span>
        </button>

        {showSquad && (
          <div style={{
            background: C.card, border: `1px solid ${C.border}`, borderRadius: 12,
            padding: 14, marginBottom: 16, boxShadow: "0 1px 3px rgba(0,0,0,.06)",
          }}>
            {POS.map(p => (
              <div key={p} style={{ marginBottom: 12 }}>
                <div style={{
                  fontSize: 11, fontWeight: 700, color: C.card, background: POS_COLOR[p],
                  display: "inline-block", padding: "2px 8px", borderRadius: 4, marginBottom: 6,
                  letterSpacing: "0.05em",
                }}>{p}</div>
                {squad.filter(x => x.pos === p).map(pl => (
                  <div key={pl.id} style={{ display: "flex", gap: 6, marginBottom: 4 }}>
                    <input style={{ ...inp, flex: 3, fontSize: 13 }} value={pl.name}
                      onChange={e => setSquad(squad.map(s => s.id === pl.id ? { ...s, name: e.target.value } : s))} />
                    <input style={{ ...inp, flex: 1, fontSize: 13, textTransform: "uppercase", textAlign: "center" }} value={pl.club}
                      onChange={e => setSquad(squad.map(s => s.id === pl.id ? { ...s, club: e.target.value.toUpperCase() } : s))} />
                    <input style={{ ...inp, flex: 1, fontSize: 13, textAlign: "right" }} type="number" step="0.1" value={pl.price}
                      onChange={e => setSquad(squad.map(s => s.id === pl.id ? { ...s, price: parseFloat(e.target.value) || 0 } : s))} />
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}

        {/* GW cards */}
        {plan.map((g, i) => {
          const s = steps[i];
          const bad = s.errs.length > 0;
          return (
            <div key={i} style={{
              background: C.card, border: `1px solid ${bad ? C.red : C.border}`,
              borderRadius: 12, padding: 16, marginBottom: 12,
              boxShadow: bad ? `0 0 0 1px ${C.red}` : "0 1px 3px rgba(0,0,0,.06)",
            }}>
              {/* GW header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{
                    background: C.accent, color: C.green, fontFamily: MONO,
                    fontSize: 13, fontWeight: 800, padding: "3px 10px", borderRadius: 6,
                  }}>GW{s.gw}</span>
                </div>
                <div style={{ fontFamily: MONO, fontSize: 12, color: C.dim, display: "flex", gap: 8, alignItems: "center" }}>
                  <span>FT <b style={{ color: C.text }}>{s.avail}</b></span>
                  <span>\u00b7</span>
                  <span>Using <b style={{ color: C.text }}>{s.used}</b></span>
                  {s.hits > 0 && <><span>\u00b7</span><span style={{ color: C.red, fontWeight: 700 }}>{s.hits * -4}pts</span></>}
                  <span>\u00b7</span>
                  <span>\u00a3<b style={{ color: s.money < 0 ? C.red : C.greenDark }}>{s.money.toFixed(1)}</b></span>
                </div>
              </div>

              {/* transfers */}
              {g.moves.map((m, k) => (
                <div key={k} style={{
                  background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8,
                  padding: 10, marginBottom: 8,
                }}>
                  <label style={lbl}>Out</label>
                  <select style={{ ...inp, marginBottom: 8 }} value={m.outId}
                    onChange={e => {
                      const p = s.snapshot.find(x => String(x.id) === e.target.value) || squad.find(x => String(x.id) === e.target.value);
                      setMove(i, k, { outId: p ? p.id : e.target.value, outName: p ? p.name : "", inPos: m.inPos || (p ? p.pos : "") });
                    }}>
                    {s.snapshot.map(p => <option key={p.id} value={p.id}>{p.pos} \u00b7 {p.name} ({p.club}) \u00a3{p.price.toFixed(1)}</option>)}
                  </select>
                  <label style={lbl}>In</label>
                  <div style={{ display: "flex", gap: 6 }}>
                    <input style={{ ...inp, flex: 3 }} placeholder="Name" value={m.inName} onChange={e => setMove(i, k, { inName: e.target.value })} />
                    <input style={{ ...inp, flex: 1, textTransform: "uppercase", textAlign: "center" }} placeholder="CLUB" value={m.inClub}
                      onChange={e => setMove(i, k, { inClub: e.target.value.toUpperCase() })} />
                    <input style={{ ...inp, flex: 1, textAlign: "right" }} type="number" step="0.1" placeholder="\u00a3" value={m.inPrice}
                      onChange={e => setMove(i, k, { inPrice: e.target.value })} />
                  </div>
                  <button style={{ background: "none", border: "none", color: C.red, fontSize: 11, fontWeight: 600, cursor: "pointer", marginTop: 8, padding: 0 }}
                    onClick={() => dropMove(i, k)}>\u2715 Remove</button>
                </div>
              ))}

              <button style={{ ...btnOutline, width: "100%", marginBottom: 10, fontSize: 12 }}
                onClick={() => addMove(i)}>+ Add transfer</button>

              {/* captain + chip */}
              <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                <div style={{ flex: 2 }}>
                  <label style={lbl}>Captain</label>
                  <select style={inp} value={g.captain} onChange={e => setGW(i, { captain: e.target.value })}>
                    <option value="">\u2014</option>
                    {s.snapshot.map(p => <option key={p.id} value={p.name}>{p.name}</option>)}
                  </select>
                </div>
                <div style={{ flex: 2 }}>
                  <label style={lbl}>Chip</label>
                  <select style={inp} value={g.chip} onChange={e => setGW(i, { chip: e.target.value })}>
                    <option value="">\u2014</option>
                    {["Wildcard", "Free Hit", "Bench Boost", "Triple Captain"].map(c => <option key={c}>{c}</option>)}
                  </select>
                </div>
              </div>

              <input style={inp} placeholder="Notes\u2026" value={g.note} onChange={e => setGW(i, { note: e.target.value })} />

              {bad && (
                <div style={{ marginTop: 10, background: "#fef2f2", borderRadius: 6, padding: 8 }}>
                  {s.errs.map((e, j) => <div key={j} style={{ fontSize: 12, color: C.red, fontWeight: 500, marginBottom: 2 }}>\u26a0 {e}</div>)}
                </div>
              )}
            </div>
          );
        })}

        {/* hits summary */}
        <div style={{ textAlign: "right", fontSize: 13, fontWeight: 600, color: totalHits ? C.red : C.greenDark, margin: "12px 0 16px", fontFamily: MONO }}>
          Planned hits: {totalHits * -4} pts
        </div>

        {/* action buttons */}
        <div style={{ display: "flex", gap: 8 }}>
          <button style={{ ...btn, flex: 1, background: C.accent }} onClick={buildExport}>Build summary</button>
          <button style={{ ...btnOutline, padding: "10px 14px" }} onClick={reset}>Reset</button>
        </div>

        {exportText && (
          <div style={{ marginTop: 14 }}>
            <label style={lbl}>Copy into chat before each deadline</label>
            <textarea readOnly value={exportText}
              style={{ ...inp, height: 240, fontSize: 12, lineHeight: 1.5, fontFamily: MONO, resize: "vertical" }}
              onFocus={e => e.target.select()} />
          </div>
        )}
      </div>
    </div>
  );
}
