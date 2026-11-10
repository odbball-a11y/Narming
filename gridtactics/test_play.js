// Checks the JS engine in play.html: rule cases, then bot-vs-bot stats to compare with analyze.py (draft 0.4).
// Run: node gridtactics/test_play.js [games]
const fs = require("fs"), path = require("path"), assert = require("assert");
const html = fs.readFileSync(path.join(__dirname, "play.html"), "utf8");
const src = html.slice(html.indexOf("// ENGINE START"), html.indexOf("// ENGINE END"));
const E = new Function(src + "\nreturn Engine;")();

function blank() { const s = E.newGame(); s.units = []; s.log = []; return s; }
function put(s, k, o, sq) { const x = E.COLS.indexOf(sq[0]), y = E.H - Number(sq.slice(1));
  const u = { id: s.nextId++, k, o, x, y, hp: E.STATS[k].hp, moved: false, acted: false }; s.units.push(u); return u; }
const at = (sq) => [E.COLS.indexOf(sq[0]), E.H - Number(sq.slice(1))];
const reachSq = (s, u) => E.reach(s, u).map(p => E.sq(p.x, p.y)).sort();

let n = 0; const t = (name, fn) => { fn(); n++; };
t("start position and scores", () => { const s = E.newGame();
  assert.deepStrictEqual(s.units.map(u => u.k + E.sq(u.x, u.y)), ["Bd2", "Se2", "Af2", "Bc9", "Sd9", "Ae9"]);
  assert.deepStrictEqual(s.vp, [0, 2]); assert.strictEqual(s.actionsLeft, 5); });
t("zone of control stops movement; walls and units block", () => { const s = blank();
  const b = put(s, "B", 0, "c5"); put(s, "S", 1, "c8");
  const r = reachSq(s, b); assert(r.includes("c6") && !r.includes("c7"));      // c7 is a wall
  const s2 = blank(); const b2 = put(s2, "B", 0, "d4"); put(s2, "A", 1, "d7");
  const r2 = reachSq(s2, b2); assert(r2.includes("d6") && !r2.includes("e7") && r2.includes("e6")); });
t("first strike, charge, counter", () => { const s = blank();
  const b = put(s, "B", 0, "h3"), sp = put(s, "S", 1, "h6");
  E.move(s, b, ...at("h5"), 2); assert.strictEqual(b.hp, 4);                     // first strike 2
  E.attack(s, b, sp, 2); assert.strictEqual(sp.hp, 2); assert.strictEqual(b.hp, 2); });  // charge 3, counter 2
t("rulebook example: archer first, then bruiser", () => { const s = blank();
  const a = put(s, "A", 0, "f5"), b = put(s, "B", 0, "h3"), sp = put(s, "S", 1, "h6");
  E.attack(s, a, sp, 0); assert.strictEqual(sp.hp, 2); assert.strictEqual(a.hp, 4);       // steady aim, no counter
  E.move(s, b, ...at("h5"), 2); assert.strictEqual(b.hp, 4);
  E.attack(s, b, sp, 2); assert(!s.units.includes(sp)); assert.strictEqual(b.hp, 4); assert.strictEqual(s.actionsLeft, 3); });
t("archer: no steady aim on a unit that moved; can't hit adjacent; high ground", () => { const s = blank();
  const a = put(s, "A", 0, "a1"), e = put(s, "B", 1, "a4"); e.moved = true;
  assert(E.targetsFrom(s, a, a.x, a.y).includes(e)); E.attack(s, a, e); assert.strictEqual(e.hp, 4);
  const adj = put(s, "B", 1, "b1"); assert(!E.targetsFrom(s, a, a.x, a.y).includes(adj));
  const s2 = blank(); const hs = put(s2, "S", 0, "e6"), f = put(s2, "B", 1, "e8");
  assert(E.targetsFrom(s2, hs, hs.x, hs.y).includes(f)); });
t("recruit once, first action only, next to base", () => { const s = E.newGame();
  assert(!E.recruit(s, "A", ...at("a1"))); assert(E.recruit(s, "A", ...at("e2")) === false);   // e2 is next to the base but occupied
  assert(E.recruit(s, "A", ...at("d1"))); assert.strictEqual(s.reserve[0].A, 1); assert(!E.canRecruit(s));
  const s2 = E.newGame(); const b = s2.units[0]; E.move(s2, b, ...at("d3"), 1); assert(!E.canRecruit(s2)); });
t("capture wins at once; points scored at start of turn", () => { const s = blank();
  const b = put(s, "B", 0, "d8"); put(s, "B", 1, "a10"); E.move(s, b, ...at("d10"), 2);
  assert.strictEqual(s.winner, 0); assert.strictEqual(s.how, "capture");
  const s2 = blank(); put(s2, "B", 0, "a5"); put(s2, "B", 1, "h10"); s2.vp = [11, 0];
  E.endTurn(s2); assert.strictEqual(s2.winner, null); E.endTurn(s2); assert.strictEqual(s2.winner, 0); assert.strictEqual(s2.how, "points"); });
t("wipe out only when the reserve is empty too", () => { const s = blank();
  const b = put(s, "B", 0, "d5"), a = put(s, "A", 1, "d6"); a.hp = 2;
  E.attack(s, b, a); assert.strictEqual(s.winner, null);
  const s2 = blank(); s2.reserve[1] = { B: 0, S: 0, A: 0 }; const b2 = put(s2, "B", 0, "d5"), a2 = put(s2, "A", 1, "d6"); a2.hp = 2;
  E.attack(s2, b2, a2); assert.strictEqual(s2.winner, 0); });
console.log(`${n} rule checks passed`);

// Bot vs bot, all style pairs, 60-round cap, bot tuned exactly as in gridsim.py
E.opt.simCompat = true;
const games = Number(process.argv[2] || 810), styles = Object.keys(E.STYLES), rounds = [], ends = {}; let p1 = 0, done = 0;
for (let i = 0; i < games; i++) {
  const st = [styles[Math.floor(i / 3) % 3], styles[i % 3]], s = E.newGame();
  while (s.winner === null && s.round <= 60) { E.botRecruit(s, st[s.turn]); while (E.botStep(s, st[s.turn])); if (s.winner === null) E.endTurn(s); }
  ends[s.how || "unfinished"] = (ends[s.how || "unfinished"] || 0) + 1;
  if (s.winner !== null) { done++; rounds.push(s.round); if (s.winner === 0) p1++; }
}
rounds.sort((a, b) => a - b);
const q = p => rounds[Math.floor(p * (rounds.length - 1))];
console.log(`bot vs bot: median ${q(.5)} rounds (80%: ${q(.1)}-${q(.9)}), Blue wins ${(100 * p1 / done).toFixed(0)}%, ends`,
  Object.fromEntries(Object.entries(ends).map(([k, v]) => [k, (100 * v / games).toFixed(0) + "%"])));
