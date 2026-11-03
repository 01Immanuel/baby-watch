# Failures found and fixed

Both rounds were found by writing vignettes from clinical reasoning (not from the rules) and running the engine on them.

## Round 1: rules 0.1.0 -> 0.1.1 (29 vignettes)
Before: 28/29 exact, go-now recall 10/11, 1 under-triage (see eval_v0.1.0_before_fix.md).
- C28: severe headache plus face/hand swelling with BP not measured came out Watch, expected Go now.
- Cause: the pre-eclampsia rules needed a measured BP or blurred vision. BP is often missing in low-resource settings.
- Fix: rule G12 (headache + swelling is Go now regardless of BP).

## Round 2: rules 0.2.0-a -> 0.2.0 (47 vignettes, after adding reading freshness)
Before: 41/47 exact, go-now recall 15/17, 3 under-triage, 3 over-triage (see eval_v0.2.0_before_fix.md).

| Case | Problem | Fix |
|---|---|---|
| C38 too weak to get up, no fever | Low (under-triage) | W13: too weak alone is Watch |
| C46 blurred vision + raised BP, no headache | Watch (under-triage) | G13: Go now |
| C47 blurred vision + face swelling, no BP | Watch (under-triage) | G14: Go now |
| C39 looks a little pale, current Hb normal | Watch (over-triage) | W04 only when Hb is unknown |
| C40 looks very pale, current Hb normal | Go now (over-triage) | G09 only when Hb is unknown or low; W14 gives Watch |
| C41 tired and dizzy, current Hb normal | Watch (over-triage) | W05 only when Hb is unknown or low |

After: 47/47 exact, go-now recall 17/17, 0 under-triage, 0 over-triage, every rule exercised by at least one vignette (eval_report.md).

## Caveat
These are my own vignettes and my own labels. The fixes are real, but the recall figure only means something once a clinician has reviewed the labels and the set reaches 40 to 60.
