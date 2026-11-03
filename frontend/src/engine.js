// Baby Watch rule engine (JS). Runs in the browser, so the result works offline.
// Mirrors backend/app/engine.py; parity is tested against rules/parity.json.
export const LEVELS = ['low', 'watch', 'go_now']
const RANK = { low: 0, watch: 1, go_now: 2 }
export const BOOLS = [
  'fatigue', 'dizzy_faint', 'palpitations', 'breathless_rest', 'vaginal_bleeding',
  'severe_headache', 'blurred_vision', 'swelling_face_hands', 'fever', 'too_weak',
  'severe_abdominal_pain', 'convulsions', 'previous_complications',
]
const NUM = /^ *-?[0-9]+(\.[0-9]+)? *$/

const num = (v) => {
  if (v === null || v === undefined || typeof v === 'boolean') return null
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  if (typeof v === 'string' && NUM.test(v)) return Number(v)
  return null
}
const age = (v, allowed, dflt) => (v === null || v === undefined ? dflt : typeof v === 'string' && allowed.includes(v) ? v : 'earlier')
const trimester = (w) => (w === null ? null : w < 14 ? 1 : w < 28 ? 2 : 3)

function anaemiaGrade(hb, tri, cfg) {
  if (hb === null) return null
  const c = cfg.by_trimester[tri ? String(tri) : 'default'] || cfg.by_trimester.default
  if (hb < cfg.severe_below) return 'severe'
  if (hb < c.moderate_below) return 'moderate'
  if (hb < c.any_below) return 'mild'
  return 'none'
}

function bpLevel(s, d, cfg) {
  if (s === null && d === null) return null
  if ((s !== null && s >= cfg.severe_sys) || (d !== null && d >= cfg.severe_dia)) return 'severe'
  if ((s !== null && s >= cfg.raised_sys) || (d !== null && d >= cfg.raised_dia)) return 'raised'
  return 'normal'
}

export function derive(inp, rules) {
  if (!inp || typeof inp !== 'object' || Array.isArray(inp)) inp = {}
  const f = {}
  for (const k of BOOLS) f[k] = inp[k] === true
  f.pallor = ['none', 'some', 'severe'].includes(inp.pallor) ? inp.pallor : 'none'
  const weeks = num(inp.gestation_weeks)
  const hb = num(inp.hb)
  const dist = num(inp.distance_km)
  const bpAge = age(inp.bp_age, ['today', 'earlier'], 'today')
  const hbAge = age(inp.hb_age, ['recent', 'earlier'], 'recent')
  f.trimester = trimester(weeks)
  const grade = anaemiaGrade(hb, f.trimester, rules.hb_cutoffs)
  const bp = bpLevel(num(inp.bp_sys), num(inp.bp_dia), rules.bp_cutoffs)
  f.anaemia_grade = hbAge === 'recent' ? grade : null
  f.hb_earlier_low = hbAge === 'earlier' && ['mild', 'moderate', 'severe'].includes(grade)
  f.bp_level = bpAge === 'today' ? bp : null
  f.bp_earlier_high = bpAge === 'earlier' && ['raised', 'severe'].includes(bp)
  f.hb_measured = f.anaemia_grade !== null
  f.bp_measured = f.bp_level !== null
  f.far_from_facility = dist !== null && dist >= rules.far_km
  return f
}

function match(c, f) {
  if (c.all) return c.all.every((x) => match(x, f))
  if (c.any) return c.any.some((x) => match(x, f))
  const v = f[c.f]
  if ('eq' in c) return v === c.eq
  if ('in' in c) return c.in.includes(v)
  throw new Error('bad condition')
}

export function evaluate(rules, inp) {
  const f = derive(inp, rules)
  const fired = rules.rules.filter((r) => match(r.when, f))
  let level = 'low'
  for (const r of fired) if (RANK[r.level] > RANK[level]) level = r.level
  const flags = rules.flags.filter((fl) => match(fl.when, f) && (fl.only_levels || LEVELS).includes(level))
  const incomplete = level === 'low' && !(f.hb_measured && f.bp_measured)
  const triggered = fired.length
    ? fired.map((r) => ({ id: r.id, level: r.level, short: r.short, why: r.why, passages: r.passages }))
    : [{ id: 'L00', level: 'low', short: 'No danger signs', why: rules.default_why, passages: rules.default_passages }]
  return {
    level,
    incomplete,
    level_info: rules.level_info[incomplete ? 'low_incomplete' : level],
    anaemia_grade: f.anaemia_grade,
    bp_level: f.bp_level,
    triggered,
    flags: flags.map((x) => ({ id: x.id, kind: x.kind, ask: x.ask ?? null, text: x.text, passages: x.passages })),
  }
}

export const signature = (r) => ({
  level: r.level, incomplete: r.incomplete, anaemia_grade: r.anaemia_grade, bp_level: r.bp_level,
  triggered: r.triggered.map((t) => t.id), flags: r.flags.map((x) => x.id),
})

export const maxLevel = (a, b) => (RANK[a] >= RANK[b] ? a : b)
