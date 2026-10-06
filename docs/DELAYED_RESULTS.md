# Delayed official results and confirmed disqualification

6 October production check found paper ticket 166445a4-8b11-4499-934a-3dae1cf5ff1c
still pending for RIKSTOTO:S3_NR_2026-10-03:6, selected #7 Donato Crown.
The public Rikstoto complete result explicitly has isComplete=true, #7 place=0,
kmTime=Dsk and positive odds=18. Other zero-place runners have Str and odds=0.
Official winner #8 has a published Dividends Winner payout of 4.82.

Winner settlement now treats only this exact, uniquely matched Dsk/zero-place/
positive-odds contract as a confirmed loss, with complete results and published
winner dividend still required. Scratch, plain zero finish, missing selection and
unconfirmed payout remain pending. The result's display odds are not substituted
for a missing closing quote; closing price and CLV remain unknown.

Nightly research also retries older frozen decisions with missing outcomes.
Backlog results require isComplete=true. New evaluations are materialized for
previously unevaluated races after their outcomes arrive. Existing historical
evaluations and frozen decision inputs are not rewritten. These retries are
reported in outcome collection counters; daily metrics retain their racing-day
filter. No model, staking, thresholds or real-money authority changes.

Live evidence:
https://www.rikstoto.no/api/results/raceDays/S3_NR_2026-10-03/6/completeresults
https://www.rikstoto.no/api/results/racedays/S3_NR_2026-10-03/raceresults
