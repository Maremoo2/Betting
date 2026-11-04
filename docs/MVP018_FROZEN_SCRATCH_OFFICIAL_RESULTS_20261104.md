# MVP-018 | Correct official full-field comparison for PRE-frozen scratches

## Root cause and exactly four original false mismatches

The original DEV-013 scorecard in [ordinary CORE-003 run 41826490000](https://github.com/Maremoo2/Betting/actions/runs/41826490000), artifact `13320200641`, `index.json` SHA256 `a7cc16d026ea08e0042dc4d6c5c2d75d3212bfd5fb00203dbbbbc36455f11d2b`, classified **four** physical races `OFFICIAL_ACTIVE_FIELD_MISMATCH`.

Original SHA-verified `shadow.json` had already marked the listed horses `scratched=true` **before T−4**; those horses were excluded from the full-field normalized Champion and CORE-004 probability vectors, and each active field sums to 1.0. Original official `completeresults` contained those *same* horses as `place=0`, `kmTime="Str"`. The old `_official_winner` compared **all** official result rows to frozen **active-only** starters, falsely rejecting these four.

| Physical race | SHA-pinned model source run / artifact | Active frozen | Original frozen scratches = official `Str` | Official winner | Complete original SHA |
| --- | --- | ---: | --- | --- | --- |
| `RIKSTOTO:S2_NR_2026-11-02:1` | 41488067799 / 13162906690 | 10 | #10 Grim Vendil, #11 Wing Tsun Brodde | #6 Rabalder Diablo | `f274f47f661e3014722a4ecdb3176bb842423e37608a38f6faa7dbffe0f4271d` |
| `RIKSTOTO:S2_NR_2026-11-02:2` | 41492573978 / 13164543152 | 7 | #2 Palmer Scott | #5 Papa Hocke | `bfe0510d302433cc6308725b880aa259065598d1bd323687c3fcf1d91a869700` |
| `RIKSTOTO:S2_NR_2026-11-02:4` | 41499820309 / 13168417335 | 11 | #9 Intercooler | #1 Håsjökometen | `8d450b154abb85e1973bbcce2af8432444a0bef8df9a5845e5ed7483c4535afe` |
| `RIKSTOTO:S2_NR_2026-11-03:9` | 41708503913 / 13267816642 | 11 | #4 Bubble Queen | #5 Fleetfoot S.S. | `7545e5b4d8c8c211add28f7c7ac203909872d10922a8e344fce54d54e71f84b5` |

Original `/raceresults` hashes are independently checked by CI through unchanged original receipts embedded in the scorecard; both original result role URIs and exact `sha256` are enforced.

## Narrow software change and rigorous negative gates

Only `src/hbi/prospective_outcome_scorecard.py` was changed. `_official_winner` receives the **entire unchanged prestart frozen roster** in addition to its already eligible active field. Every official result number must correspond to a member of that frozen roster. If an official row belongs to a frozen scratched horse, it must be `place=0`, `kmTime="Str"` **and match the frozen original horseName exactly ignoring only case/trailing whitespace**. The originally active horses must still all appear and match their immutable names. Only the *previously excluded* frozen scratches are ignored when selecting winner. Missing/extra runners, after-freeze scratches, duplicate start numbers, contradictory name, incorrect scratched result code or multiple winners still fail closed. No new provider source, model refit, model freeze, PIT status, stake, betting decision, or historical result state is written.

Original regression tests use four authentic GitHub model artifacts and original complete/raceday bytes with SHA-backed original receipts from baseline scorecard. Synthetic negative tests cover invalid late scratch (formerly active), field omission, unknown runner, duplicate, wrong scratch status, false scratched number/name. Main prediction model and market inputs stay completely unchanged.

**Expected controlled result (not yet operationally measured):** Existing four 4/4 full-field model pairs and their pre-T−4 WIN vectors may become officially result-evaluable: baseline **16 → 20** original-result model pairs and **14 → 18** common-frozen-WIN triples if no other blocker arises when the entire cumulative pipeline is rerun. This remains an **implementation hypothesis until exact CI and subsequent actual ordinary main operation**. Other 27 missing model freezes and 8/6 fullfield-source blocked races remain unchanged; no historical original is created or modified.

**No merge without explicit owner approval.**
