import { useState, useEffect } from "react";

/* ─── palette ─── */
const C = {
  bg: "#f8f9fa",
  card: "#ffffff",
  border: "#e2e6ea",
  accent: "#37003c",
  accentLight: "#f0e6f2",
  green: "#00ff87",
  greenDark: "#02894e",
  red: "#e63946",
  yellow: "#f4a300",
  text: "#1a1a2e",
  dim: "#6c757d",
};

const SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
const MONO = 'ui-monospace, "SF Mono", Menlo, Consolas, monospace';
const POS_COLOR = { GK: "#f4a300", DEF: "#04f5ff", MID: "#00ff87", FWD: "#e63946" };

const MODE_META = {
  SHIELD: { color: "#0077b6" },
  SAFE: { color: C.greenDark },
  BALANCED: { color: C.yellow },
  AGGRESSIVE: { color: "#e76f00" },
  SWING: { color: C.red },
  "SEASON OVER": { color: C.dim },
};

const KEY = "fpl:planner:v3";
const TUTORIAL_KEY = "fpl:planner:tutorial_seen_v2";

/* ─── persistence ─── */
function loadState() {
  try { const raw = localStorage.getItem(KEY); return raw ? JSON.parse(raw) : null; }
  catch { return null; }
}
function saveState(data) {
  try { localStorage.setItem(KEY, JSON.stringify(data)); return true; }
  catch { return false; }
}

/* ─── tutorial ─── */
const TUTORIAL_STEPS = [
  {
    title: "What is this?",
    body: "The planner shows your backroom staff's recommended transfer plans for the next 5 gameweeks. They're generated automatically from the daily brief.",
  },
  {
    title: "Three paths",
    body: "Toggle between Safe (minimal moves, no hits), Balanced (a few calculated moves), and Aggressive (more moves, hits if needed). Pick the path that matches your risk dial.",
  },
  {
    title: "Review each gameweek",
    body: "Each card shows what transfers happen that week, your FT balance, and any blanks or double gameweeks. Moves show xPts gain and the reason behind them.",
  },
  {
    title: "Tweak the plan",
    body: "Disagree with a move? Remove it, or add your own. The planner recalculates FT rollover, budget, and hit costs automatically.",
  },
  {
    title: "Export and act",
    body: "Hit 'Export plan' to get a text summary you can paste into a GitHub issue. Your backroom staff (Claude) reads it and confirms or challenges your decisions.",
  },
];

function Tutorial({ onClose }) {
  const [step, setStep] = useState(0);
  const s = TUTORIAL_STEPS[step];
  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,.55)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 1000, padding: 20,
    }} onClick={onClose}>
      <div style={{
        background: "#fff", borderRadius: 16, padding: "28px 24px 20px",
        maxWidth: 380, width: "100%", boxShadow: "0 20px 60px rgba(0,0,0,.3)",
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: C.accent, textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Step {step + 1} of {TUTORIAL_STEPS.length}
          </span>
          <button onClick={onClose} style={{ background: "none", border: "none", color: C.dim, fontSize: 18, cursor: "pointer", padding: 0 }}>
            {"×"}
          </button>
        </div>
        <h3 style={{ fontSize: 18, fontWeight: 700, color: C.text, margin: "8px 0 8px", fontFamily: SANS }}>{s.title}</h3>
        <p style={{ fontSize: 14, color: C.dim, lineHeight: 1.6, margin: "0 0 20px" }}>{s.body}</p>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <button onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}
            style={{ background: "none", border: "none", color: step === 0 ? C.border : C.accent, fontSize: 13, fontWeight: 600, cursor: step === 0 ? "default" : "pointer", padding: 0 }}>
            {"← Back"}
          </button>
          <div style={{ display: "flex", gap: 5 }}>
            {TUTORIAL_STEPS.map((_, i) => (
              <div key={i} style={{ width: 8, height: 8, borderRadius: "50%", background: i === step ? C.accent : C.border }} />
            ))}
          </div>
          {step < TUTORIAL_STEPS.length - 1 ? (
            <button onClick={() => setStep(step + 1)}
              style={{ background: C.accent, color: "#fff", border: "none", borderRadius: 6, padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
              {"Next →"}
            </button>
          ) : (
            <button onClick={onClose}
              style={{ background: C.greenDark, color: "#fff", border: "none", borderRadius: 6, padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
              Got it
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── move card ─── */
function MoveCard({ move, onRemove }) {
  const posColor = POS_COLOR[move.out.pos] || C.dim;
  const xptsGain = (move.in.xpts != null && move.out.xpts != null)
    ? (move.in.xpts - move.out.xpts).toFixed(1) : null;
  return (
    <div style={{
      background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8,
      padding: 12, marginBottom: 8, borderLeft: `3px solid ${posColor}`,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: C.red, textTransform: "uppercase" }}>Out</span>
            <span style={{ fontSize: 14, fontWeight: 600, color: C.text }}>{move.out.name}</span>
            <span style={{ fontSize: 12, color: C.dim }}>({move.out.club})</span>
            <span style={{ fontSize: 12, color: C.dim, fontFamily: MONO }}>{"£"}{move.out.price.toFixed(1)}</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: C.greenDark, textTransform: "uppercase" }}>In</span>
            <span style={{ fontSize: 14, fontWeight: 600, color: C.text }}>{move.in.name}</span>
            <span style={{ fontSize: 12, color: C.dim }}>({move.in.club})</span>
            <span style={{ fontSize: 12, color: C.dim, fontFamily: MONO }}>{"£"}{move.in.price.toFixed(1)}</span>
            {move.in.owned != null && <span style={{ fontSize: 11, color: C.dim }}>{move.in.owned.toFixed(0)}% owned</span>}
          </div>
        </div>
        <div style={{ textAlign: "right", minWidth: 60 }}>
          {xptsGain !== null && (
            <div style={{ fontSize: 13, fontWeight: 700, fontFamily: MONO, color: parseFloat(xptsGain) > 0 ? C.greenDark : C.red }}>
              {parseFloat(xptsGain) > 0 ? "+" : ""}{xptsGain}
              <div style={{ fontSize: 9, fontWeight: 500, color: C.dim }}>xPts</div>
            </div>
          )}
          {move.is_hit && <div style={{ fontSize: 10, fontWeight: 700, color: C.red, marginTop: 2 }}>HIT {"−4"}</div>}
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 6 }}>
        <span style={{ fontSize: 11, color: C.dim, fontStyle: "italic" }}>{move.reason}</span>
        {onRemove && (
          <button onClick={onRemove} style={{ background: "none", border: "none", color: C.red, fontSize: 11, fontWeight: 600, cursor: "pointer", padding: 0 }}>
            {"✕"}
          </button>
        )}
      </div>
    </div>
  );
}

/* ─── GW card ─── */
function GWCard({ gwData, moves, edits, onEditChange }) {
  const blanks = gwData.blanks || [];
  const doubles = gwData.doubles || [];
  const hasInfo = blanks.length > 0 || doubles.length > 0;
  const hits = gwData.hits || 0;

  return (
    <div style={{
      background: C.card, border: `1px solid ${C.border}`, borderRadius: 12,
      padding: 16, marginBottom: 12, boxShadow: "0 1px 3px rgba(0,0,0,.06)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: moves.length > 0 || hasInfo ? 12 : 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{
            background: C.accent, color: C.green, fontFamily: MONO,
            fontSize: 13, fontWeight: 800, padding: "3px 10px", borderRadius: 6,
          }}>GW{gwData.gw}</span>
          {gwData.rolled && <span style={{ fontSize: 12, color: C.greenDark, fontWeight: 600 }}>Roll FT</span>}
        </div>
        <div style={{ fontFamily: MONO, fontSize: 12, color: C.dim, display: "flex", gap: 6, alignItems: "center" }}>
          <span>FT <b style={{ color: C.text }}>{gwData.ft_avail}</b></span>
          <span>{"·"}</span>
          <span>Using <b style={{ color: C.text }}>{gwData.used}</b></span>
          {hits > 0 && <><span>{"·"}</span><span style={{ color: C.red, fontWeight: 700 }}>{hits * -4}pts</span></>}
        </div>
      </div>

      {hasInfo && (
        <div style={{ display: "flex", gap: 8, marginBottom: moves.length > 0 ? 10 : 0 }}>
          {blanks.length > 0 && (
            <span style={{ fontSize: 11, color: C.red, fontWeight: 600, background: "#fef2f2", padding: "2px 8px", borderRadius: 4 }}>
              {"⚠"} Blank: {blanks.join(", ")}
            </span>
          )}
          {doubles.length > 0 && (
            <span style={{ fontSize: 11, color: C.greenDark, fontWeight: 600, background: "#ecfdf5", padding: "2px 8px", borderRadius: 4 }}>
              DGW: {doubles.join(", ")}
            </span>
          )}
        </div>
      )}

      {moves.map((m, i) => (
        <MoveCard key={i} move={m} onRemove={edits ? () => edits.removeMove(gwData.gw, i) : null} />
      ))}

      {edits && (
        <div style={{ display: "flex", gap: 8, marginTop: moves.length > 0 ? 4 : 0 }}>
          <select style={{
            flex: 1, background: C.bg, color: C.dim, border: `1px solid ${C.border}`,
            borderRadius: 6, padding: "6px 8px", fontSize: 12, fontFamily: SANS,
          }}
            value="" onChange={e => { if (e.target.value) onEditChange(gwData.gw, "captain", e.target.value); }}>
            <option value="">Captain...</option>
            {(edits.squad || []).filter(p => p.status === "a").map(p => (
              <option key={p.id} value={p.name}>{p.name}</option>
            ))}
          </select>
          <select style={{
            background: C.bg, color: C.dim, border: `1px solid ${C.border}`,
            borderRadius: 6, padding: "6px 8px", fontSize: 12, fontFamily: SANS,
          }}
            value="" onChange={e => { if (e.target.value) onEditChange(gwData.gw, "chip", e.target.value); }}>
            <option value="">Chip...</option>
            {["Wildcard", "Free Hit", "Bench Boost", "Triple Captain"].map(c => <option key={c}>{c}</option>)}
          </select>
        </div>
      )}

      {edits?.gwEdits?.[gwData.gw]?.captain && (
        <div style={{ marginTop: 6, fontSize: 12, color: C.accent, fontWeight: 600 }}>
          {"Captain: "}{edits.gwEdits[gwData.gw].captain}
          <button onClick={() => onEditChange(gwData.gw, "captain", "")}
            style={{ background: "none", border: "none", color: C.dim, fontSize: 11, cursor: "pointer", marginLeft: 6 }}>{"✕"}</button>
        </div>
      )}
      {edits?.gwEdits?.[gwData.gw]?.chip && (
        <div style={{ marginTop: 4, fontSize: 12, color: C.yellow, fontWeight: 600 }}>
          {"Chip: "}{edits.gwEdits[gwData.gw].chip}
          <button onClick={() => onEditChange(gwData.gw, "chip", "")}
            style={{ background: "none", border: "none", color: C.dim, fontSize: 11, cursor: "pointer", marginLeft: 6 }}>{"✕"}</button>
        </div>
      )}
    </div>
  );
}

/* ─── main app ─── */
export default function App() {
  const [brief, setBrief] = useState(null);
  const [path, setPath] = useState("balanced");
  const [status, setStatus] = useState("Loading...");
  const [showTutorial, setShowTutorial] = useState(false);
  const [exportText, setExportText] = useState("");
  const [removedMoves, setRemovedMoves] = useState({});  // {path: {gw: [indices]}}
  const [gwEdits, setGwEdits] = useState({});  // {gw: {captain, chip}}

  useEffect(() => {
    if (!localStorage.getItem(TUTORIAL_KEY)) setShowTutorial(true);
  }, []);

  const closeTutorial = () => {
    setShowTutorial(false);
    localStorage.setItem(TUTORIAL_KEY, "1");
  };

  useEffect(() => {
    // Load saved edits
    const saved = loadState();
    if (saved) {
      if (saved.path) setPath(saved.path);
      if (saved.removedMoves) setRemovedMoves(saved.removedMoves);
      if (saved.gwEdits) setGwEdits(saved.gwEdits);
    }

    // Fetch brief data
    fetch("./data/brief.json")
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data && data.plans) {
          setBrief(data);
          setStatus(`Brief from ${data.date}`);
        } else if (data) {
          setBrief(data);
          setStatus("Brief loaded (no plans — pre-season)");
        } else {
          setStatus("No brief data available");
        }
      })
      .catch(() => setStatus("Could not load brief data"));
  }, []);

  // Save edits
  useEffect(() => {
    saveState({ path, removedMoves, gwEdits });
  }, [path, removedMoves, gwEdits]);

  const plan = brief?.plans?.[path];
  const dial = brief?.dial || {};
  const modeColor = MODE_META[dial.mode]?.color || C.dim;

  const getActiveMoves = (gw) => {
    if (!plan) return [];
    const removed = removedMoves[path]?.[gw] || [];
    return plan.moves
      .filter(m => m.gw === gw)
      .filter((_, i) => !removed.includes(i));
  };

  const removeMove = (gw, index) => {
    setRemovedMoves(prev => {
      const next = { ...prev };
      if (!next[path]) next[path] = {};
      if (!next[path][gw]) next[path][gw] = [];
      // Find the actual index in the original moves array
      const gwMoves = plan.moves.filter(m => m.gw === gw);
      const removed = prev[path]?.[gw] || [];
      let realIndex = 0;
      let visibleCount = 0;
      for (let i = 0; i < gwMoves.length; i++) {
        if (!removed.includes(i)) {
          if (visibleCount === index) { realIndex = i; break; }
          visibleCount++;
        }
      }
      next[path][gw] = [...(next[path][gw] || []), realIndex];
      return next;
    });
  };

  const onEditChange = (gw, field, value) => {
    setGwEdits(prev => ({
      ...prev,
      [gw]: { ...(prev[gw] || {}), [field]: value },
    }));
  };

  const totalHits = plan ? plan.ft_sequence.reduce((sum, s) => {
    const activeMoves = getActiveMoves(s.gw);
    const hits = Math.max(0, activeMoves.length - s.ft_avail);
    return sum + hits;
  }, 0) : 0;

  const buildExport = () => {
    if (!plan || !brief) return;
    const L = [];
    const gw1 = brief.gw;
    L.push(`FPL PLAN — GW${gw1}–GW${gw1 + 4} (${path.toUpperCase()} path)`);
    L.push(`Mode: ${dial.mode} (${dial.behind} behind, ${dial.left} GWs left)`);
    L.push(`Total hits: ${totalHits} (${totalHits * -4} pts)`);
    L.push("");

    L.push("SQUAD");
    const POS = ["GK", "DEF", "MID", "FWD"];
    POS.forEach(p => {
      const players = (brief.squad || []).filter(x => x.pos === p);
      if (players.length) {
        L.push(`${p}: ${players.map(x => `${x.name} (${x.club}) £${x.price.toFixed(1)}`).join(" · ")}`);
      }
    });
    L.push("");

    plan.ft_sequence.forEach(s => {
      const moves = getActiveMoves(s.gw);
      const edits = gwEdits[s.gw] || {};
      const hits = Math.max(0, moves.length - s.ft_avail);
      L.push(`GW${s.gw} — FT ${s.ft_avail}, using ${moves.length}${hits ? `, ${hits} hit(s)` : ""}`);
      if (moves.length === 0) {
        L.push("  Roll FT");
      } else {
        moves.forEach(m => {
          const hitTag = m.is_hit ? " (HIT)" : "";
          L.push(`  OUT ${m.out.name} (${m.out.club}, £${m.out.price.toFixed(1)}) → IN ${m.in.name} (${m.in.club}, £${m.in.price.toFixed(1)})${hitTag}`);
          L.push(`       ${m.reason}`);
        });
      }
      if (edits.captain) L.push(`  Captain: ${edits.captain}`);
      if (edits.chip) L.push(`  Chip: ${edits.chip}`);
      const blanks = s.blanks || [];
      const doubles = s.doubles || [];
      if (blanks.length) L.push(`  ⚠ Blanks: ${blanks.join(", ")}`);
      if (doubles.length) L.push(`  DGW: ${doubles.join(", ")}`);
    });
    setExportText(L.join("\n"));
  };

  const resetEdits = () => {
    setRemovedMoves({});
    setGwEdits({});
    setExportText("");
  };

  /* ─── styles ─── */
  const btn = {
    background: C.accent, color: "#fff", border: "none", borderRadius: 8,
    padding: "10px 16px", fontFamily: SANS, fontSize: 13, fontWeight: 600, cursor: "pointer",
  };
  const btnOutline = { ...btn, background: "transparent", color: C.accent, border: `1.5px solid ${C.accent}` };
  const inp = {
    background: C.bg, color: C.text, border: `1px solid ${C.border}`,
    borderRadius: 8, padding: "8px 10px", fontFamily: SANS, fontSize: 14,
    width: "100%", boxSizing: "border-box",
  };
  const lbl = {
    fontFamily: SANS, fontSize: 11, fontWeight: 600, color: C.dim,
    textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 4,
  };

  const hasPlan = plan && plan.ft_sequence && plan.ft_sequence.length > 0;
  const preseason = plan && plan.summary && plan.summary.includes("Pre-season");

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

      {showTutorial && <Tutorial onClose={closeTutorial} />}

      {/* header */}
      <div style={{ background: C.accent, padding: "14px 16px", marginBottom: 20 }}>
        <div style={{ maxWidth: 540, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 20, fontWeight: 800, color: C.green, letterSpacing: "-0.02em" }}>fpld</span>
            <span style={{ fontSize: 14, fontWeight: 500, color: "rgba(255,255,255,.7)" }}>planner</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button onClick={() => setShowTutorial(true)}
              style={{ background: "rgba(255,255,255,.15)", border: "none", color: "rgba(255,255,255,.7)", fontSize: 12, fontWeight: 600, cursor: "pointer", padding: "4px 10px", borderRadius: 6 }}>?</button>
            <span style={{ fontSize: 11, color: "rgba(255,255,255,.5)", fontFamily: MONO }}>{status.toUpperCase()}</span>
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 540, margin: "0 auto", padding: "0 16px" }}>

        {/* risk dial summary */}
        {dial.mode && (
          <div style={{
            background: C.card, border: `1px solid ${C.border}`, borderRadius: 12,
            padding: 16, marginBottom: 16, borderLeft: `4px solid ${modeColor}`,
            boxShadow: "0 1px 3px rgba(0,0,0,.06)",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ fontSize: 20, fontWeight: 800, color: modeColor }}>{dial.mode}</div>
                <div style={{ fontSize: 13, color: C.dim, marginTop: 2 }}>{dial.gloss}</div>
              </div>
              <div style={{ textAlign: "right", fontFamily: MONO, fontSize: 12, color: C.dim }}>
                <div>{dial.behind} pts behind</div>
                <div>{dial.left} GWs left</div>
              </div>
            </div>
          </div>
        )}

        {/* path toggle */}
        <div style={{ display: "flex", gap: 4, marginBottom: 16, background: C.card, borderRadius: 10, padding: 4, border: `1px solid ${C.border}` }}>
          {["safe", "balanced", "aggressive"].map(p => (
            <button key={p} onClick={() => { setPath(p); setExportText(""); }}
              style={{
                flex: 1, padding: "10px 0", borderRadius: 8, border: "none",
                fontFamily: SANS, fontSize: 13, fontWeight: 700, cursor: "pointer",
                textTransform: "uppercase", letterSpacing: "0.04em",
                background: path === p ? C.accent : "transparent",
                color: path === p ? "#fff" : C.dim,
              }}>
              {p}
            </button>
          ))}
        </div>

        {/* plan summary */}
        {plan && (
          <div style={{ fontSize: 13, color: C.dim, marginBottom: 16, padding: "0 4px" }}>
            {preseason
              ? "Pre-season — plans will generate once GW1 has been scored."
              : plan.summary}
          </div>
        )}

        {!brief && (
          <div style={{
            background: C.card, border: `1px solid ${C.border}`, borderRadius: 12,
            padding: 24, textAlign: "center", color: C.dim,
          }}>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>No brief data</div>
            <div style={{ fontSize: 13, lineHeight: 1.5 }}>
              The planner needs <code>brief.json</code> from the daily pipeline.
              Run <code>python3 fpld_brief.py --json</code> or wait for the daily GitHub Action.
            </div>
          </div>
        )}

        {/* GW cards */}
        {hasPlan && !preseason && plan.ft_sequence.map((gwData, i) => (
          <GWCard
            key={i}
            gwData={gwData}
            moves={getActiveMoves(gwData.gw)}
            edits={{ removeMove, squad: brief?.squad, gwEdits }}
            onEditChange={onEditChange}
          />
        ))}

        {/* hits summary */}
        {hasPlan && !preseason && (
          <div style={{ textAlign: "right", fontSize: 13, fontWeight: 600, color: totalHits ? C.red : C.greenDark, margin: "8px 0 16px", fontFamily: MONO }}>
            Total hits: {totalHits * -4} pts
          </div>
        )}

        {/* actions */}
        {hasPlan && !preseason && (
          <>
            <div style={{ display: "flex", gap: 8 }}>
              <button style={{ ...btn, flex: 1 }} onClick={buildExport}>Export plan</button>
              <button style={{ ...btnOutline, padding: "10px 14px" }} onClick={resetEdits}>Reset edits</button>
            </div>

            {exportText && (
              <div style={{ marginTop: 14 }}>
                <label style={lbl}>Paste into your GitHub issue</label>
                <textarea readOnly value={exportText}
                  style={{ ...inp, height: 280, fontSize: 12, lineHeight: 1.5, fontFamily: MONO, resize: "vertical" }}
                  onFocus={e => e.target.select()} />
              </div>
            )}
          </>
        )}

        {/* squad (collapsed by default) */}
        {brief?.squad && (
          <details style={{ marginTop: 20 }}>
            <summary style={{
              cursor: "pointer", fontSize: 13, fontWeight: 600, color: C.accent,
              padding: "8px 0", userSelect: "none",
            }}>
              Squad ({brief.squad.length}) — {"£"}{brief.squad.reduce((a, p) => a + p.price, 0).toFixed(1)}m
            </summary>
            <div style={{
              background: C.card, border: `1px solid ${C.border}`, borderRadius: 12,
              padding: 14, marginTop: 8, boxShadow: "0 1px 3px rgba(0,0,0,.06)",
            }}>
              {["GK", "DEF", "MID", "FWD"].map(pos => {
                const players = brief.squad.filter(p => p.pos === pos);
                if (!players.length) return null;
                return (
                  <div key={pos} style={{ marginBottom: 10 }}>
                    <div style={{
                      fontSize: 11, fontWeight: 700, color: "#fff", background: POS_COLOR[pos],
                      display: "inline-block", padding: "2px 8px", borderRadius: 4, marginBottom: 4,
                    }}>{pos}</div>
                    {players.map(p => (
                      <div key={p.id} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 13 }}>
                        <span>
                          {p.name} <span style={{ color: C.dim }}>({p.club})</span>
                          {p.status !== "a" && <span style={{ color: C.red, fontWeight: 600, marginLeft: 4 }}>{"⚠"}</span>}
                        </span>
                        <span style={{ fontFamily: MONO, color: C.dim }}>{"£"}{p.price.toFixed(1)}</span>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}
