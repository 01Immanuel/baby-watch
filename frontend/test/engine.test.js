import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { evaluate, signature, derive } from '../src/engine.js'
import { validate } from '../src/validate.js'

const read = (p) => JSON.parse(fs.readFileSync(new URL(p, import.meta.url)))
const rules = read('../../rules/rules.json')
const parity = read('../../rules/parity.json')
const cases = read('../../rules/cases.json').cases

test(`JS engine matches the Python engine on ${parity.length} inputs`, () => {
  parity.forEach((row, i) => assert.deepEqual(signature(evaluate(rules, row.input)), row.expected, `row ${i}`))
})

test('every labelled vignette gets its expected level', () => {
  const bad = cases.filter((c) => evaluate(rules, c.input).level !== c.expected_level).map((c) => c.id)
  assert.deepEqual(bad, [])
})

test('junk input never crashes and is Low so far', () => {
  for (const junk of [undefined, null, [], 'x', 5, true, {}]) {
    const r = evaluate(rules, junk)
    assert.equal(r.level, 'low')
    assert.equal(r.incomplete, true)
    assert.equal(r.level_info.label, 'Low so far')
  }
})

test('reading freshness: old readings never reach Go now or reassure', () => {
  assert.equal(evaluate(rules, { bp_sys: 180, bp_dia: 120, bp_age: 'earlier' }).level, 'watch')
  assert.equal(evaluate(rules, { hb: 5, hb_age: 'earlier' }).level, 'watch')
  assert.equal(evaluate(rules, { hb: 13, hb_age: 'earlier', bp_sys: 110, bp_dia: 70, bp_age: 'earlier' }).incomplete, true)
})

test('every condition field exists in derived state', () => {
  const keys = Object.keys(derive({}, rules))
  const fields = (c) => (c.all ? c.all.flatMap(fields) : c.any ? c.any.flatMap(fields) : [c.f])
  for (const item of [...rules.rules, ...rules.flags]) for (const f of fields(item.when)) assert.ok(keys.includes(f), `${item.id}: ${f}`)
})

test('validate rejects impossible numbers', () => {
  assert.ok(validate({ bp_sys: -4, bp_dia: 7, bp_age: 'today' }).bp_sys)
  assert.ok(validate({ hb: 99, hb_age: 'recent' }).hb)
  assert.ok(validate({ gestation_weeks: 0 }).gestation_weeks)
  assert.ok(validate({ bp_sys: 110, bp_dia: 120, bp_age: 'today' }).bp_dia)
  assert.ok(validate({ bp_sys: 120, bp_dia: null, bp_age: 'today' }).bp_dia)
  assert.ok(validate({ distance_km: -1 }).distance_km)
})

test('validate requires a reading date whenever a reading is entered', () => {
  assert.ok(validate({ hb: 10, bp_age: null, hb_age: null }).hb_age)
  assert.ok(validate({ bp_sys: 120, bp_dia: 80, bp_age: null }).bp_age)
  assert.deepEqual(validate({ hb: 10, hb_age: 'earlier', bp_sys: 120, bp_dia: 80, bp_age: 'today' }), {})
})

test('validate accepts normal and empty input', () => {
  assert.deepEqual(validate({ gestation_weeks: 30, distance_km: 5 }), {})
  assert.deepEqual(validate({ gestation_weeks: null, hb: null, bp_sys: null, bp_dia: null, distance_km: null }), {})
})
