# V1 operational acceptance

The acceptance workflow is triggered by this PR and can be run manually. It uses a fixed authentic 13 November cohort and only reads source artifacts and official Rikstoto result endpoints. It does not use the Windows watcher, write shared state, run the models after the race, or send mail.

## Evidence

- The 13 November Collector originals cover 25 Nordic physical races, with 25 archived fields.
- The pinned replay retains five complete WIN fields, one original research freeze and 11 horses with p(win). Eskilstuna 1 was frozen under the original T−4. Its result is linked, but scoring remains blocked because the official result marks two horses active in the freeze as scratched. No new model outcomes are inferred.
- The local offline replay from the saved official responses reproduced the report SHA-256 396703bce814bffe63d34494e568e50b8ee9a51f3e34af2b3c4a046d12e0df62. The pinned ZIPs are outside Git. The script can reread them without an Actions download when supplied the local archive and saved-result directory.
- First hosted run 43454313130 published report artifact 14053141732. The downloaded ZIP matched GitHub SHA-256 b0dde0def59608dd1819addd41f4f9de1c1094adbfb499d08b01593f58dc70c8. This proves hosted replay, official result retrieval and report publication. It is not a scheduled live acceptance.
- The original Eskilstuna PDF in artifact 14050576199 has SHA-256 ed7f0eeaa998f8dc1226ec3461beafdb3330b213a9d07e5a6f16711e80ee2400. The archive's /starts body has SHA-256 d5429c4893a14ef7e3e7b7ab5dd0c849e1e12254e16a8853b34e666bf329586e. Betting previously missed the suffix physical label on race 6's title line and read its start clock into race 5's section. Both clocks now verify against the same original bytes. Complete PDF sections improved from 6/8 to 8/8. Model admission, source clock equality and runner checks are unchanged.

## Remaining operational dependencies

The fixed acceptance workflow can replay downloaded originals. The production-grade cloud path still requires an authorized durable private archive destination and a scheduled source-to-result job with a supported data source. Ephemeral runner storage and ordinary Actions artifacts cannot provide long-term retention. The workflow publishes only derived reports. The separate #203 draft-work lineage contains Nordic queue prioritization. This PR does not merge or deploy it.

A future live run must measure the full physical denominator, record timely blocked races, prove source retention across runner replacement, recover a scoreable freeze against both result endpoints, and publish the daily report. A failed official field or timing check remains visible and must never be counted as a successful score.

## Nordic daily operations

The two draft branches can be combined cleanly from main 9f9117b. Review and approve #203 and #204 independently, then verify the combined tree and check results on the exact combined commit before any scheduling decision. #203 prioritizes NO/SE research fetches. #204 includes the PDF fix and the daily reporting layer, with no schedule enabled.

The manual date input inventories completed CORE-003 runs by Oslo day, preserves exact artifact ZIPs by pinned digest, selects a complete reporting anchor, and passes earlier cohorts to the existing report generator. Failed runs and unavailable artifacts are recorded. Every Nordic race in the Collector manifest remains visible. The existing DEV-009 result fetch and validation are reused for races with a frozen model. Result revisions are stored under independent content hashes. The fixed PR replay additionally verifies Solvalla race 10, 4 November, by recomputing all six original Champion/CORE-004/WIN scores against the two archived official responses.

Proposed disabled schedule: 03:30 UTC daily, using the previous civil date in Europe/Oslo. Before enabling it, supply an owner-approved private persistent filesystem to the hosted job, with a restricted writer and read-only replay access. Point --archive to that mounted path and keep --stage on runner temporary storage. Verify restoration on a fresh runner without Actions download permissions and confirm retention and recovery after a real artifact expiry. The current GitHub runner directory expires with the job. No private raw originals are uploaded to GitHub Actions.

The 13 November replay covers 25 physical races, eight with inspected model dispositions and 17 evening races absent from those cohorts. It preserves the one Eskilstuna research freeze and five complete WIN fields. The Eskilstuna result remains unscored. The PDF repair restores two source sections but creates no historical predictions. More model coverage requires an ordinary timed execution covering Kalmar and Biri, plus verification of the remaining Swedish model source/field blockers.
