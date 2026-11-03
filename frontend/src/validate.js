// Input checks shared by the form. Ranges match the backend (backend/app/main.py).
export const LIMITS = {
  gestation_weeks: [1, 45, 'Weeks pregnant'],
  hb: [2, 20, 'Haemoglobin'],
  bp_sys: [50, 300, 'Blood pressure (top)'],
  bp_dia: [30, 200, 'Blood pressure (bottom)'],
  distance_km: [0, 1000, 'Distance'],
}

export function validate(input) {
  const errors = {}
  for (const [k, [lo, hi, label]] of Object.entries(LIMITS)) {
    const v = input[k]
    if (v === null || v === undefined) continue
    if (!Number.isFinite(v)) errors[k] = `${label}: enter a number.`
    else if (v < lo || v > hi) errors[k] = `${label} must be between ${lo} and ${hi}.`
  }
  const hasSys = input.bp_sys != null
  const hasDia = input.bp_dia != null
  if (hasSys !== hasDia) {
    errors.bp_dia = 'Blood pressure: enter both the top and bottom numbers, or leave both empty.'
  } else if (!errors.bp_sys && !errors.bp_dia && hasSys && input.bp_dia >= input.bp_sys) {
    errors.bp_dia = 'Blood pressure: the bottom number must be lower than the top number.'
  }
  if ((hasSys || hasDia) && !input.bp_age) errors.bp_age = 'Say when the blood pressure was taken.'
  if (input.hb != null && !input.hb_age) errors.hb_age = 'Say when the blood test was done.'
  return errors
}
