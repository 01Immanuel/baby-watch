import { useEffect, useRef, useState } from 'react'
import rules from '@rules/rules.json'
import corpus from '@rules/corpus.json'
import { evaluate, maxLevel } from './engine.js'
import { validate } from './validate.js'

const DANGER = [
  ['vaginal_bleeding', 'Bleeding from the vagina'],
  ['convulsions', 'Fits (convulsions)'],
  ['severe_headache', 'Severe headache'],
  ['blurred_vision', 'Blurred vision'],
  ['swelling_face_hands', 'Swelling of face or hands'],
  ['severe_abdominal_pain', 'Severe belly pain'],
  ['fever', 'Fever'],
  ['too_weak', 'Too weak to get out of bed'],
  ['breathless_rest', 'Short of breath even at rest'],
]
const ALSO = [
  ['fatigue', 'Very tired'],
  ['dizzy_faint', 'Dizzy or fainting'],
  ['palpitations', 'Heart beating very fast'],
  ['previous_complications', 'Problem in an earlier pregnancy', 'Heavy bleeding after birth, pre-eclampsia, stillbirth or caesarean'],
]
const SIGN_LABEL = Object.fromEntries([...DANGER, ...ALSO].map(([k, t]) => [k, t]))
const PALLOR = [['none', 'Normal'], ['some', 'A little pale'], ['severe', 'Very pale']]
const HB_WHEN = [['recent', `Last ${rules.freshness.hb_recent_weeks} weeks`], ['earlier', 'Older']]
const BP_WHEN = [['today', 'Today'], ['earlier', 'Earlier']]
const CLINIC_QUESTIONS = ['What is my haemoglobin (blood level)?', 'What is my blood pressure?', 'Do I need iron tablets?']
const LEVELS = ['low', 'watch', 'go_now']
const RANK = { low: 0, watch: 1, go_now: 2 }
const EMPTY = { gestation_weeks: '', hb: '', bp_sys: '', bp_dia: '', distance_km: '', pallor: 'none', hb_when: '', bp_when: '' }
const PASSAGE = Object.fromEntries(corpus.passages.map((p) => [p.id, p]))
const toNum = (v) => (v === '' ? null : Number(v))
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s)
const CAN_SPEAK = typeof window !== 'undefined' && 'speechSynthesis' in window
const MODES = [['woman', 'Woman or family'], ['worker', 'Health worker']]
const COPY = {
  woman: {
    lede: 'Tick what is happening. Baby Watch tells you whether to wait, get checked, or go now. It does not diagnose.',
    dangerH: 'Is any of this happening now?',
    dangerSub: 'Tick all that apply.',
    alsoH: 'Also tick if true',
    palloH: 'How pale does she look?',
    palloSub: 'Look inside the eyelids, at the palms and nails.',
    numbers: 'I have numbers from a clinic card or pharmacy',
    numbersSub: 'Optional. Without them the best result is \u201cLow so far\u201d.',
    askH: 'Ask for',
    share: 'Show family',
    copy: 'Copy message',
    note: 'This is not a diagnosis. A health worker must check her.',
    fine: 'Summaries of WHO guidance. This is not a replacement for a health worker. If you are worried, go to a facility.',
  },
  worker: {
    lede: 'Record what you see and any measured values. Baby Watch returns Low, Watch or Go now, with the WHO rule behind it. It does not diagnose.',
    dangerH: 'Danger signs present now',
    dangerSub: 'Tick all that the patient reports or you observe.',
    alsoH: 'Also present',
    palloH: 'Pallor',
    palloSub: 'Check the inside of the eyelids, the palms and the nails.',
    numbers: 'Measured values (haemoglobin, blood pressure)',
    numbersSub: 'Enter values measured at this visit or recorded on the card. Without them the best result is \u201cLow so far\u201d.',
    askH: 'Recommend',
    share: 'Referral note',
    copy: 'Copy note',
    note: 'Decision aid based on WHO guidance. Not a diagnosis. Clinical judgement applies.',
    fine: 'Decision aid based on WHO guidance summaries. It does not replace clinical judgement or local protocols.',
  },
}

function savedMode() {
  try { return localStorage.getItem('bw-mode') === 'worker' ? 'worker' : 'woman' } catch { return 'woman' }
}

async function fetchExplain(input, clientLevel) {
  const ctl = new AbortController()
  const t = setTimeout(() => ctl.abort(), 9000)
  try {
    const r = await fetch('/api/explain', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: ctl.signal,
      body: JSON.stringify({ input, client_level: clientLevel }),
    })
    if (!r.ok) { const e = new Error('status ' + r.status); e.status = r.status; throw e }
    return await r.json()
  } finally { clearTimeout(t) }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    try { document.execCommand('copy') } finally { document.body.removeChild(ta) }
  }
}

function Field({ id, label, unit, value, onChange, error, inputMode = 'numeric' }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className={'control' + (error ? ' bad' : '')}>
        <input id={id} type="number" inputMode={inputMode} value={value} onChange={onChange} aria-invalid={!!error} />
        {unit && <span className="unit">{unit}</span>}
      </div>
    </div>
  )
}

function Row({ checked, onToggle, label, hint }) {
  return (
    <label className={'row' + (checked ? ' on' : '')}>
      <input type="checkbox" className="vh" checked={checked} onChange={onToggle} />
      <span className="text">{label}{hint && <small>{hint}</small>}</span>
      <span className="mark" aria-hidden="true" />
    </label>
  )
}

function Segmented({ name, label, value, onChange, options, error }) {
  return (
    <>
      <fieldset className={'segmented' + (error ? ' bad' : '')} aria-label={label} style={{ gridTemplateColumns: `repeat(${options.length}, 1fr)` }}>
        {options.map(([v, t]) => (
          <label key={v} className={value === v ? 'on' : ''}>
            <input type="radio" className="vh" name={name} checked={value === v} onChange={() => onChange(v)} />{t}
          </label>
        ))}
      </fieldset>
    </>
  )
}

function Scale({ level, label }) {
  const at = RANK[level]
  return (
    <div className="scale" role="img" aria-label={`${label}, on a scale of Low, Watch, Go now`}>
      {LEVELS.map((l, i) => (
        <div key={l} className={'step' + (i <= at ? ' filled' : '') + (i === at ? ' here' : '')} style={{ '--i': i }}>
          <span className="bar" />
          <span className="name">{rules.level_info[l].label}</span>
        </div>
      ))}
    </div>
  )
}

const Svg = ({ children, size = 20 }) => (
  <svg className="ic" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
)
const IconUsers = () => (<Svg><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></Svg>)
const IconVolume = () => (<Svg><path d="M11 5 6 9H2v6h4l5 4V5z" /><path d="M15.5 8.5a5 5 0 0 1 0 7" /><path d="M19 5a10 10 0 0 1 0 14" /></Svg>)
const IconStop = () => (<Svg><rect x="6" y="6" width="12" height="12" rx="2" /></Svg>)
const IconCopy = () => (<Svg><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></Svg>)
const Logo = () => (
  <svg className="logo" width="34" height="34" viewBox="0 0 64 64" aria-hidden="true">
    <rect width="64" height="64" rx="14" fill="currentColor" />
    <polyline points="10.9,33.3 23,33.3 27.5,21.1 33.3,45.4 38.4,27.5 41.6,33.3 53.1,33.3" fill="none" stroke="#fff" strokeWidth="4.2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

export default function App() {
  const [form, setForm] = useState(EMPTY)
  const [signs, setSigns] = useState({})
  const [result, setResult] = useState(null)
  const [server, setServer] = useState({ state: 'idle' })
  const [errors, setErrors] = useState({})
  const [mode, setMode] = useState(savedMode)
  const [numbersOpen, setNumbersOpen] = useState(() => savedMode() === 'worker')
  const [checked, setChecked] = useState(null)
  const [speaking, setSpeaking] = useState(false)
  const [copied, setCopied] = useState(false)
  const resultRef = useRef(null)
  const errRef = useRef(null)
  const famRef = useRef(null)

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const worker = mode === 'worker'
  const tx = COPY[mode]
  const pickMode = (m) => {
    setMode(m)
    setNumbersOpen(m === 'worker')
    try { localStorage.setItem('bw-mode', m) } catch { /* private mode: the choice just is not remembered */ }
  }
  const toggle = (k) => () => setSigns({ ...signs, [k]: !signs[k] })

  async function check(e) {
    e.preventDefault()
    const input = {
      gestation_weeks: toNum(form.gestation_weeks), hb: toNum(form.hb),
      bp_sys: toNum(form.bp_sys), bp_dia: toNum(form.bp_dia),
      distance_km: toNum(form.distance_km), pallor: form.pallor, ...signs,
    }
    if (input.bp_sys !== null || input.bp_dia !== null) input.bp_age = form.bp_when || null
    if (input.hb !== null) input.hb_age = form.hb_when || null
    const errs = validate(input)
    setErrors(errs)
    if (Object.keys(errs).length) {
      if (['hb', 'hb_age', 'bp_sys', 'bp_dia', 'bp_age'].some((k) => errs[k])) setNumbersOpen(true)
      setResult(null); setChecked(null); setServer({ state: 'idle' }); return
    }
    setChecked(input)
    stopSpeaking()
    const local = evaluate(rules, input) // instant, works offline
    setResult(local)
    setServer({ state: 'loading' })
    try {
      const s = await fetchExplain(input, local.level)
      setServer({ state: 'ok', data: s })
    } catch (err) {
      // 422/5xx = the server answered but refused; anything else = could not reach it
      setServer({ state: err && err.status ? 'error' : 'offline', status: err && err.status })
    }
  }

  function stopSpeaking() { if (CAN_SPEAK) window.speechSynthesis.cancel(); setSpeaking(false) }
  const reset = () => {
    stopSpeaking(); setForm(EMPTY); setSigns({}); setResult(null); setErrors({}); setNumbersOpen(worker); setChecked(null)
    setServer({ state: 'idle' }); window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  useEffect(() => {
    if (Object.keys(errors).length && errRef.current) errRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [errors])
  useEffect(() => {
    if (result && resultRef.current) resultRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [result])
  useEffect(() => stopSpeaking, [])

  // Safety: if the two engines ever disagree, show the more urgent level.
  const level = result ? (server.state === 'ok' ? maxLevel(result.level, server.data.level) : result.level) : null
  const info = level ? (level === result.level ? result.level_info : rules.level_info[level]) : null
  const mismatch = server.state === 'ok' && server.data.level !== result.level
  const ordered = result ? [...result.triggered].sort((a, b) => RANK[b.level] - RANK[a.level]) : []
  const real = ordered.filter((t) => t.id !== 'L00')
  const chips = real.slice(0, 2)
  const asks = result ? result.flags.filter((f) => f.kind === 'ask') : []
  const notes = result ? result.flags.filter((f) => f.kind === 'note') : []
  const cited = new Set()
  if (result) result.triggered.forEach((t) => t.passages.forEach((p) => cited.add(p)))
  if (server.state === 'ok') server.data.passages.forEach((p) => cited.add(p.id))
  const errList = Object.values(errors)
  const cites = (t) => <span className="cite">{t.passages.map((p) => `[${p}]`).join('')}</span>

  function speak() {
    if (!CAN_SPEAK || !info) return
    if (speaking) { stopSpeaking(); return }
    const parts = [info.label + '.', info.action, info.window && cap(info.window) + '.']
    if (chips.length) parts.push('Because ' + chips.map((c) => c.short).join(', and ') + '.')
    if (asks.length) parts.push(tx.askH + ' ' + asks.map((a) => a.ask).join(', and ') + '.')
    const u = new SpeechSynthesisUtterance(parts.filter(Boolean).join(' '))
    u.lang = 'en-NG'; u.rate = 0.95; u.onend = () => setSpeaking(false); u.onerror = () => setSpeaking(false)
    window.speechSynthesis.cancel(); window.speechSynthesis.speak(u); setSpeaking(true)
  }

  const familyLine = result && {
    go_now: `A pregnant woman used Baby Watch. It says she needs to go to a health facility ${rules.level_info.go_now.window}. Please help her go.`,
    watch: `A pregnant woman used Baby Watch. It says she should be checked by a health worker ${rules.level_info.watch.window}. Please help her go.`,
    low: 'A pregnant woman used Baby Watch. It found no danger signs. She should still ask for a blood test and a blood pressure check at her next visit.',
  }[level]

  const noteLine = result && {
    go_now: `Pregnant woman. Baby Watch advises referral to a health facility ${rules.level_info.go_now.window}.`,
    watch: `Pregnant woman. Baby Watch advises assessment by a health worker ${rules.level_info.watch.window}.`,
    low: 'Pregnant woman. No danger signs found from the information entered. Make sure haemoglobin and blood pressure are checked at the next visit.',
  }[level]
  const shareLine = worker ? noteLine : familyLine
  const present = checked ? Object.keys(SIGN_LABEL).filter((k) => checked[k] === true).map((k) => SIGN_LABEL[k].toLowerCase()) : []
  const findings = checked ? [
    checked.gestation_weeks != null && `${checked.gestation_weeks} weeks pregnant`,
    present.length ? `Signs: ${present.join(', ')}` : 'No danger signs ticked',
    checked.hb != null && `Haemoglobin ${checked.hb} g/dL, ${checked.hb_age === 'recent' ? `tested in the last ${rules.freshness.hb_recent_weeks} weeks` : 'older result'}`,
    checked.bp_sys != null && checked.bp_dia != null && `Blood pressure ${checked.bp_sys}/${checked.bp_dia}, ${checked.bp_age === 'today' ? 'taken today' : 'earlier reading'}`,
    `Pallor: ${(PALLOR.find(([v]) => v === checked.pallor) || [null, 'not recorded'])[1].toLowerCase()}`,
  ].filter(Boolean) : []

  async function copyNote() {
    const stamp = new Date().toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
    const lines = [
      worker ? 'BABY WATCH REFERRAL NOTE' : 'BABY WATCH RESULT',
      stamp,
      '',
      `Result: ${info.label}`,
      shareLine,
      ...(worker && findings.length ? ['', 'Findings:', ...findings.map((x) => `- ${x}`)] : []),
      ...(real.length ? ['', 'Why:', ...real.slice(0, 3).map((t) => `- ${t.short}`)] : []),
      ...(asks.length ? ['', `${tx.askH}:`, ...asks.map((a) => `- ${a.ask}`)] : []),
      '',
      tx.note,
    ]
    await copyText(lines.join('\n'))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="page">
      <div className="hero">
        <div className="wrap">
          <header className="top">
            <div className="brand"><Logo /><span>Baby Watch</span></div>
            <button type="button" className="quiet" onClick={reset}>Clear</button>
          </header>
          <h1 className="tagline">Know when to get care.</h1>
          <p className="lede">{tx.lede}</p>
        </div>
      </div>
      <div className="app">

      <form onSubmit={check} noValidate>
        <section>
          <h2>Who is using this?</h2>
          <Segmented name="mode" label="Who is using this" value={mode} onChange={pickMode} options={MODES} />
        </section>

        <section>
          <div className="pair">
            <Field id="weeks" label="Weeks pregnant" unit="weeks" value={form.gestation_weeks} onChange={set('gestation_weeks')} error={errors.gestation_weeks} />
            <Field id="dist" label="Distance to clinic" unit="km" inputMode="decimal" value={form.distance_km} onChange={set('distance_km')} error={errors.distance_km} />
          </div>
        </section>

        <section>
          <h2>{tx.dangerH}</h2>
          <p className="sub">{tx.dangerSub}</p>
          <div className="list">
            {DANGER.map(([k, t]) => <Row key={k} checked={!!signs[k]} onToggle={toggle(k)} label={t} />)}
          </div>
        </section>

        <section>
          <h2>{tx.alsoH}</h2>
          <div className="list">
            {ALSO.map(([k, t, h]) => <Row key={k} checked={!!signs[k]} onToggle={toggle(k)} label={t} hint={h} />)}
          </div>
        </section>

        <section>
          <h2>{tx.palloH}</h2>
          <p className="sub">{tx.palloSub}</p>
          <Segmented name="pallor" label="Paleness" value={form.pallor} onChange={(v) => setForm({ ...form, pallor: v })} options={PALLOR} />
        </section>

        <section>
          <details className="numbers" open={numbersOpen} onToggle={(e) => setNumbersOpen(e.currentTarget.open)}>
            <summary>{tx.numbers}</summary>
            <p className="sub">{tx.numbersSub}</p>

            <div className="numblock">
              <Field id="hb" label="Haemoglobin" unit="g/dL" inputMode="decimal" value={form.hb} onChange={set('hb')} error={errors.hb} />
              <p className="when-label">When was it tested?</p>
              <Segmented name="hb_when" label="When haemoglobin was tested" value={form.hb_when} onChange={(v) => setForm({ ...form, hb_when: v })} options={HB_WHEN} error={errors.hb_age} />
            </div>

            <div className="numblock">
              <div className="field">
                <label htmlFor="bps">Blood pressure</label>
                <div className={'control bp' + (errors.bp_sys || errors.bp_dia ? ' bad' : '')}>
                  <input id="bps" type="number" inputMode="numeric" aria-label="Blood pressure, top number" value={form.bp_sys} onChange={set('bp_sys')} />
                  <span className="slash" aria-hidden="true">/</span>
                  <input id="bpd" type="number" inputMode="numeric" aria-label="Blood pressure, bottom number" value={form.bp_dia} onChange={set('bp_dia')} />
                </div>
              </div>
              <p className="when-label">When was it taken?</p>
              <Segmented name="bp_when" label="When blood pressure was taken" value={form.bp_when} onChange={(v) => setForm({ ...form, bp_when: v })} options={BP_WHEN} error={errors.bp_age} />
              <p className="hint">Blood pressure changes through the day. Only a reading from today counts as current. To measure: sit, rest 5 minutes, arm level with your heart.</p>
            </div>
          </details>
        </section>

        {errList.length > 0 && (
          <div className="errors" role="alert" ref={errRef}>
            <p>Fix these, then check again.</p>
            <ul>{errList.map((m) => <li key={m}>{m}</li>)}</ul>
          </div>
        )}

        <div className="bar-cta">
          <button type="submit" className="primary">Check</button>
        </div>
      </form>

      {result && (
        <section className={'result ' + level} aria-live="polite" ref={resultRef}>
          <p className="level">{info.label}</p>
          <Scale level={level} label={info.label} />
          <p className="act">{info.action}</p>
          {info.window && <p className="when">{info.window}</p>}
          {mismatch && <p className="notice">The two checks disagreed. The more urgent result is shown.</p>}

          {chips.length > 0 && (
            <div className="because">
              <span className="k">Because</span>
              <ul className="chips">{chips.map((c) => <li key={c.id}>{c.short}</li>)}</ul>
            </div>
          )}

          {asks.length > 0 && (
            <div className="ask">
              <span className="k">{tx.askH}</span>
              <ul>{asks.map((a) => <li key={a.id}>{a.ask}</li>)}</ul>
            </div>
          )}
          {notes.map((f) => <p key={f.id} className="flag">{f.text}</p>)}

          <div className="tools">
            <button type="button" onClick={() => famRef.current && famRef.current.showModal()}><IconUsers />{tx.share}</button>
            {CAN_SPEAK && <button type="button" onClick={speak} aria-pressed={speaking}>{speaking ? <><IconStop />Stop</> : <><IconVolume />Read aloud</>}</button>}
          </div>

          <div className="drawers">
            <details>
              <summary>Why this result</summary>
              <ul className="why">{ordered.map((t) => <li key={t.id}>{t.why} {cites(t)}</li>)}</ul>
            </details>

            {asks.length > 0 && !worker && (
              <details>
                <summary>Questions to ask at the clinic</summary>
                <ul className="why">{CLINIC_QUESTIONS.map((q) => <li key={q}>{q}</li>)}</ul>
              </details>
            )}

            <details>
              <summary>Explain in plain words {server.state === 'ok' && server.data.explanation_mode === 'llm' && <small className="tag">AI-written, cited</small>}</summary>
              {server.state === 'loading' && <p className="muted">Writing the explanation…</p>}
              {server.state === 'offline' && <p className="muted"><span className="tag">No connection</span> The explanation server is not reachable. The result above does not need it.</p>}
              {server.state === 'error' && server.status === 429 && <p className="muted"><span className="tag">Too many requests</span> Wait a minute and try again. The result above is still valid.</p>}
              {server.state === 'error' && server.status !== 429 && <p className="muted"><span className="tag">Server error {server.status}</span> The explanation failed. The result above is still valid.</p>}
              {server.state === 'ok' && server.data.explanation_mode === 'llm' && <p className="explain">{server.data.explanation}</p>}
              {server.state === 'ok' && server.data.explanation_mode === 'template' && (
                <p className="muted">No AI explanation this time. The reasons above come straight from the rules.
                  {server.data.explanation_note !== 'no LLM key set' && <span className="small"> AI not used: {server.data.explanation_note}.</span>}
                </p>
              )}
            </details>

            <details>
              <summary>Sources ({cited.size})</summary>
              <ul className="sources">
                {[...cited].sort().map((id) => PASSAGE[id] && (
                  <li key={id}><b>[{id}]</b> {PASSAGE[id].doc} ({PASSAGE[id].year}), {PASSAGE[id].section}. <span className="muted">{PASSAGE[id].text}</span></li>
                ))}
              </ul>
            </details>
          </div>
          <p className="muted small fine">{tx.fine}</p>
        </section>
      )}

      {result && (
        <dialog ref={famRef} className={'family ' + level} aria-label={worker ? 'Referral note' : 'Result to show family'}>
          <p className="level">{info.label}</p>
          <p className="fam-line">{shareLine}</p>
          {chips.length > 0 && <><p className="k">Why</p><ul>{real.slice(0, 3).map((t) => <li key={t.id}>{t.short}</li>)}</ul></>}
          {worker && findings.length > 0 && <><p className="k">Findings</p><ul>{findings.map((x) => <li key={x}>{x}</li>)}</ul></>}
          {asks.length > 0 && <><p className="k">{tx.askH}</p><ul>{asks.map((a) => <li key={a.id}>{a.ask}</li>)}</ul></>}
          <p className="fam-note">{tx.note}</p>
          <p className="fam-time">{new Date().toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}</p>
          <div className="tools">
            <button type="button" onClick={copyNote}><IconCopy />{copied ? 'Copied' : tx.copy}</button>
          </div>
          <button type="button" className="primary" onClick={() => famRef.current.close()}>Close</button>
        </dialog>
      )}
      </div>
    </div>
  )
}
