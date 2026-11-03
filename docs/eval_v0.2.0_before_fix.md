# Baby Watch: rule engine evaluation on synthetic vignettes

Cases: 47 (synthetic, NOT yet clinician reviewed). Rules version: 0.2.0-a.

- Exact agreement: 41/47
- Go-now recall: 15/17
- Watch-or-higher recall (any risk caught): 38/39
- Under-triage (engine lower than expected): 3
- Over-triage (engine higher than expected): 3
- Rules never triggered by any vignette: none

## Under-triage cases
- C38: expected watch, engine low. too weak to get out of bed, no fever
- C46: expected go_now, engine watch. blurred vision with raised BP today, no headache
- C47: expected go_now, engine watch. blurred vision with face swelling, BP not measured

## Over-triage cases
- C39: expected low, engine watch. looks a little pale but current Hb is normal
- C40: expected watch, engine go_now. looks very pale but current Hb is normal: recheck, not emergency
- C41: expected low, engine watch. tired and dizzy but current Hb is normal

