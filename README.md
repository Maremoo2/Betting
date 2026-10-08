# Horse Betting Intelligence

A Benter-first horse-racing research and decision-support system.

Historical market collection: [Rikstoto Crawler Pre-winner](docs/RIKSTOTO_PRE_WINNER.md).
It masks results until PRE freeze and keeps archive research separate from live decisions.

**Active betting standard: Betting V3.3.** Use `betting review` or `hbi review-betting`.
Full-field probability intervals and an independent PLACE model are required inputs;
they are never inferred from HBI/PRE-WATCH scores. Divergence is evidence only.
See [the V3.3 contract and prospective workflow](docs/BETTING_V3_3.md).
The frozen Champion/watcher continues as a historical research comparator; its V2.1
paper decisions are not V3.3 approvals. `hbi review-contenders` is the legacy V2.1
replay interface. No V3.3 decision can submit a real wager.

Scheduled ChatGPT research is connected through a narrow **research-only evidence bridge**: qualitative pre-watch findings enter an append-only GitHub issue inbox (with an optional Google Sheets mirror) and are validated into canonical SQLite research records, but the LLM cannot overwrite odds, results, probabilities, decisions, stakes or settlement. See [docs/INTELLIGENCE_BRIDGE.md](docs/INTELLIGENCE_BRIDGE.md).

The project separates:

- a **market-free fundamental model**
- **race-difficulty / reject-option** diagnostics
- **static market probabilities**
- **market-path intelligence** across pre-race time states
- **model-market conflict / shrinkage**
- a calibrated **combined probability**
- price / EV / execution decisions
- frozen outcomes and calibration research

The system is deliberately conservative: AI/ML is used to improve data quality,
feature extraction, validation and automation. It does not replace the core
probability/market discipline.

## Data ownership

The HBI database is the canonical source of truth. The repository now contains a
SQLite persistence layer over `db/schema.sql`. Race cards, runners, immutable market
snapshots and frozen model predictions can be stored locally and later moved to a
server database without changing the modelling contract.

Google Sheets/Drive is intentionally treated as an optional dashboard/import-export
surface, **not** the primary database. A spreadsheet is useful for human review, but
it is a poor canonical store for high-frequency timestamped market snapshots and
frozen model history.

Provider-neutral interfaces in `src/hbi/ingestion.py` remain the modelling boundary.
A read-only Rikstoto adapter is now implemented behind that boundary. Its endpoint
provenance is explicit: user-verified, open-source-observed, or historical-frontend
inferred. Provider failures are logged; missing values are never fabricated.

## Current V1 system foundation

Implemented in this repository:

- point-in-time and source-provenance validation primitives
- normalized full-field market probabilities
- Benter-style second-stage probability-combination primitive
- separate race-difficulty / reject-option diagnostics
- timestamped market-path and material-change pre-watch logic
- structured review flags for material qualitative events
- persistent SQLite storage with idempotent snapshots and frozen predictions
- provider-neutral race/market ingestion contracts
- read-only Rikstoto raceday + V/P/TV/T market collection
- live-smoke-verified Rikstoto `/starts` canonical race fields
- capability-based international ATG market-free enrichment
- strict FULL_FIELD_ONLY admission; Sweden, Denmark, Norway and France trot live-verified
- market-free `FUNDAMENTAL_CHAMPION_V1_1` shadow probabilities
- best-effort T-4 shadow watcher every five minutes
- immutable shadow ticket ledger and nightly settlement/report
- [V2.1 Contender Gate](docs/CONTENDER_GATE_V2_1.md): mandatory pricing audit,
  late-price WATCH downgrade, and separate Winner/coupon consistency review
- Research Observatory v1 with data-health, calibration, model-vs-market and CLV/P&L reporting
- immutable nightly SQLite + CSV + JSON research backups with integrity hashes
- **market-only benchmark** for log-loss and Brier evaluation
- decision-price vs closing-price / CLV evaluation primitive
- Brier/log-loss/calibration helpers
- champion/challenger model governance
- machine-readable P0/P1 research governance
- future-mutation temporal-integrity regression audit
- frozen runtime replay-parity audit
- settlement reconciliation integrity audit
- deterministic research learning dataset
- run/code/policy/schema provenance manifests
- challenger-specific forward-validation clocks
- recommendation-only promotion readiness gate
- research-only counterfactual engine
- centralized input-eligibility gate before value evaluation
- SQLite-compatible canonical schema
- CI with Ruff + Pytest

See [ARCHITECTURE.md](ARCHITECTURE.md).


## Full roadmap: from raw racing data to a validated autonomous betting system

This roadmap describes the intended end-state of HBI and the order in which it should
be built. The percentages below are **project-priority heuristics**, not empirical
claims that a fixed share of long-run betting profit can be attributed to one layer.

The core research principle remains Benter-first:

1. build the strongest point-in-time **market-free fundamental probability estimate**
   that the data can support;
2. treat the betting market as an additional information source rather than an enemy
   to ignore;
3. combine model and market only after both are measured independently;
4. bet only when the executable price is sufficiently above fair value;
5. evaluate on untouched races and never infer skill from hit rate or a short P/L run.

The current implementation is intentionally conservative. A feature is not valuable
because it sounds sophisticated, and a model is not good because it uses many
variables. Commercial horse-racing AI descriptions often advertise 50+ variables and
some broader descriptions cite feature sets approaching 100–200 variables per race.
HBI treats that only as evidence that rich racing systems can be data-heavy, **not**
as evidence that more variables automatically improve prediction or profitability.

### Roadmap overview

| Phase | Objective | Current state | Promotion / completion gate |
| --- | --- | --- | --- |
| 1. Data collection | Build a complete point-in-time racing and market dataset | **ACTIVE / partially complete** | High coverage, source provenance, leakage tests, full-field identity integrity |
| 2. Prediction engine | Produce calibrated full-field p(win) and beat market-only benchmarks | **Shadow Champion v1.1 active** | Untouched OOS improvement in log loss/Brier/calibration and economic evidence |
| 3. LLM intelligence layer | Convert unstructured information into auditable evidence and explanations | **Framework present, production feature use limited** | Source-backed extraction quality and no direct LLM production p(win) |
| 4. Risk and portfolio management | Size wagers and control drawdown/exposure | **Research-only / future gate** | Validated edge estimates, pool impact, fractional-Kelly research and exposure controls |
| 5. Automated execution | Verify live price, submit, reconcile and learn automatically | **Not implemented; real-money authority OFF** | Legal/provider access, execution parity, safety gates and explicit manual approval |

---

### 1. Data collection — highest immediate priority (~40% of roadmap value)

The first major competitive advantage is not a more complicated neural network. It is
a cleaner, broader and more accurately timestamped dataset than the decision system
would otherwise have.

HBI should continuously collect and preserve, when a reliable point-in-time source is
available:

- each horse's historical starts, wins, placings, earnings and recent form;
- race-by-race performance, distance, surface, class and pace/split data where
  available;
- jockey/driver history, recent form and horse/track/distance combinations;
- trainer history, recent form and relevant stable changes;
- track, surface and going/baneforhold;
- weather and material weather changes;
- start position/draw, start method, distance and handicap/additional distance;
- declared field, scratches, jockey/driver changes and equipment changes where
  available;
- early odds, decision-time odds and closing odds;
- complete odds/market path rather than only one snapshot;
- pool/liquidity information where a verified provider contract exposes it;
- bookmaker/exchange/tote prices when they can be captured legally and reliably;
- live market movement and market disagreement;
- verified injuries, withdrawals, veterinary notices and other material changes;
- official final result and dividend/closing-price data for settlement.

**Current implementation:** Rikstoto is the canonical race/market source. ATG is used
as a read-only market-free enrichment source only when the entire active field can be
matched safely. Sweden, Denmark, Norway and France trot are live-verified for full-field
enrichment. French fields also require LeTROT career-count corroboration. Other
combinations remain disabled until reviewed full-field live verification.

The international target is not "support every country". The target is:

```text
Rikstoto race
    -> canonical field
    -> approved enrichment providers
    -> identity resolution
    -> all active runners complete?
         yes -> expose fundamentals
         no  -> FIELD_ONLY / NOT_EXECUTABLE
```

One missing active runner must never be silently imputed from odds or from a generic
average merely to increase betting volume.

#### Phase 1A — canonical racing history

Build a durable longitudinal store keyed by stable horse identity so that HBI can
derive its own strictly chronological history rather than depending forever on one
provider's current summary fields.

Target feature families:

- prior starts / wins / placings;
- recency-weighted form;
- distance-specific form;
- track/surface-specific form;
- class movement;
- earnings and strength-of-competition proxies;
- layoff/rest patterns;
- age/sex development curves;
- race density and durability;
- driver/jockey and trainer combinations.

Every derived feature must be reproducible with:

```text
feature_as_of < target race start
```

and must pass future-mutation invariance so that changing future races cannot change a
historical feature.

#### Phase 1B — context and environment

Add verified contextual data only when it can be joined reliably:

- weather;
- track/going;
- draw/start position;
- start method;
- distance;
- race class;
- field size;
- scratches;
- driver/jockey changes;
- equipment changes where an authoritative source exists.

Weather and going should be timestamped independently. "Today's final weather" must
never be backfilled into an earlier decision as though it had been known at T-30.

#### Phase 1C — market path

Benter's core insight is especially important here: the public market contains real
information that a fundamental model will never fully observe. HBI therefore stores
market information separately from the fundamental feature set.

Desired time states include, when available:

```text
T-60
T-30
T-15
T-10
T-5
T-4 decision
T-2
T-1
close
```

Research questions include:

- how much does the market improve as race start approaches?
- when does late movement add information beyond the fundamental model?
- is early "steam" actually predictive after controlling for closing price?
- how much CLV does a decision capture?
- how stable is available price between observation and execution?
- which countries, tracks and pool sizes have usable liquidity?

Market movement is evidence. It is never automatically labelled "smart money".

#### Phase 1D — information/event layer

Create structured evidence events for:

- scratches;
- rider/driver changes;
- trainer comments;
- veterinary/injury information;
- track-condition changes;
- meaningful weather changes;
- equipment changes;
- other verified late material information.

This is the first place where the LLM layer can add substantial value: extracting a
structured, sourced event from text. The LLM must not convert that event directly into
an unreviewed production probability.

#### Phase 1 completion gate

Phase 1 is mature when HBI can demonstrate:

- stable identities across a large share of the target racing universe;
- high full-field feature coverage rather than partial-runner cherry-picking;
- exact source/provenance for every critical feature;
- reproducible point-in-time features;
- low provider failure rates;
- reliable market snapshots and official settlement;
- explicit missingness instead of fabricated values;
- country/track/provider coverage reports;
- temporal-integrity and runtime-replay audits passing continuously.

---

### 2. Prediction engine — calibrated probabilities, not winner picks

The model's primary output is a **full-field probability distribution**:

| Runner | Example p(win) | Fair decimal odds |
| --- | ---: | ---: |
| Horse 5 | 32% | 3.13 |
| Horse 3 | 18% | 5.56 |
| Horse 8 | 14% | 7.14 |

The objective is not to say "Horse 5 wins". The objective is to estimate every
runner's probability accurately enough that the system can identify mispricing.

For a fixed decimal price, the basic expected-value relation is:

```text
EV per 1 unit staked = p(win) * decimal_odds - 1
```

For example, if a model estimates `p(win)=0.32` and an executable decimal price is
`5.0`:

```text
0.32 * 5.0 - 1 = +0.60
```

That is a theoretical +60% expected return **if both the probability and executable
price are correct**. In tote markets, the price itself can move as money enters the
pool, so HBI must also model closing price, liquidity and the bettor's own impact.

#### Phase 2A — frozen baseline

The current `FUNDAMENTAL_CHAMPION_V1_1` deliberately uses a small market-free
empirical feature set. Its purpose is to establish a clean prospective baseline, not
to be the final model.

It is evaluated against:

- market-only probabilities;
- combined fundamental + market probabilities;
- log loss;
- multiclass Brier score;
- calibration;
- CLV;
- P/L/ROI as a separate economic layer;
- race/track/country/odds-band slices.

#### Phase 2B — feature factory and ablation

Potential challenger feature families:

- recent horse form;
- speed/time/pace ratings;
- distance suitability;
- track/surface suitability;
- class strength and class changes;
- draw/start-position effects;
- trainer effects;
- jockey/driver effects;
- horse-rider/trainer combinations;
- rest/layoff;
- age/sex;
- race difficulty;
- weather/going interactions;
- verified equipment/health/event indicators.

Every candidate feature must prove incremental value in ablation. "More variables" is
not a promotion criterion.

#### Phase 2C — model families

Candidate model families may include:

- regularized multinomial/logistic models;
- tree boosting;
- calibrated gradient boosting;
- hierarchical models;
- neural models only when sample size and validation justify them;
- ensembles of independently useful model families.

The simplest model that survives out-of-sample testing is preferred over unnecessary
complexity.

#### Phase 2D — market model and Benter-style combination

The fundamental model must stay market-free during its own training/evaluation.

Separately:

```text
p_fundamental
p_market
        \
         -> calibrated Benter-style combination -> p_combined
```

The combination coefficients are **parameters to estimate prospectively**, not magic
defaults. The current equal-log-pool shadow combination is only a research baseline.

The central research question is:

> Does the fundamental model contain information that remains useful after the market
> is known?

If the answer is no, more model complexity does not create an edge.

#### Phase 2E — Champion/Challenger governance

A new Challenger receives its own forward clock. Races used to discover or design the
Challenger cannot be reused as its final promotion proof.

Research milestones:

- first 50–100 prospective races: pipeline/data-quality debugging;
- roughly 100–300: early calibration and slice diagnostics;
- 500+ untouched eligible races: serious Champion/Challenger evidence begins;
- larger samples are required when edge is small, variance is high or results differ
  materially by country/race type.

Promotion requires more than positive P/L. At minimum:

- P0 integrity gates pass;
- sufficient untouched forward sample;
- log loss improves versus Champion;
- Brier improves versus Champion;
- comparison against market-only baseline;
- calibration is not materially worse;
- improvement replicates across relevant slices;
- economic result survives executable-price assumptions;
- manual review approves promotion.

---

### 3. LLM layer — evidence compiler, analyst and explainer

The LLM is **not** the production p(win) engine.

Its intended roles are:

- read and classify news;
- extract structured trainer/jockey comments;
- detect material late changes;
- summarize race context;
- explain why a statistical model scored runners as it did;
- generate daily research reports;
- surface data-quality anomalies;
- suggest hypotheses for Challenger research;
- assist with provider/schema maintenance;
- compare model behavior across races and regimes.

Example:

> "Explain why the model's top runner moved from 21% to 28%, which inputs changed,
> what the market did, and whether the difference is inside the model's historical
> calibration range."

The answer should be built from frozen model data and cited evidence, not invented
handicapping intuition.

LLM-generated research hypotheses may create a Challenger proposal. They do **not**
receive execution authority automatically.

---

### 4. Risk, bankroll and portfolio management

Even a genuinely positive-expectation model can fail operationally if staking is
poor.

Future HBI risk management should include:

- bankroll state;
- maximum stake per race;
- maximum daily exposure;
- correlated exposure across multi-race products;
- country/track/product exposure caps;
- drawdown monitoring;
- model-confidence and calibration uncertainty;
- liquidity and pool-size limits;
- stake impact on pari-mutuel dividends;
- fractional-Kelly research;
- hard loss/chasing prevention;
- independent risk kill-switches.

Benter specifically warns that overestimating an edge can make Kelly sizing harmful,
that full Kelly produces severe drawdowns, and that fractional Kelly is more practical.
He also notes that in pari-mutuel markets the bettor's own wager can reduce the
dividend, meaning pool size can become a harder constraint than bankroll size.

Therefore the intended progression is:

```text
validated p(win)
    -> executable/final-price model
    -> edge uncertainty
    -> fractional Kelly candidate
    -> pool-impact cap
    -> exposure cap
    -> final permitted stake
```

A simple illustrative example such as a 100,000 NOK bankroll and a 1,500 NOK stake is
not a staking rule. Actual stake sizing must come from validated probability error,
price uncertainty, pool impact and drawdown policy.

No chasing is permitted. A previous loss cannot increase the next stake.

---

### 5. Automated execution — last phase, not the first

The future fully automated loop would be:

```text
1. discover race
2. collect/freeze all eligible pre-race information
3. estimate full-field probabilities
4. observe executable market price
5. pass integrity/value/risk gates
6. verify price immediately before submission
7. submit permitted ticket
8. record provider acknowledgement
9. reconcile official result/dividend
10. update research dataset and evaluation
```

This repository intentionally stops before step 7 today.

Before real-money automation can even be considered, HBI would require:

- a supported and permitted provider execution interface;
- explicit account/authentication separation from research code;
- idempotent ticket submission;
- exact executable-price verification;
- duplicate-bet protection;
- race-start cutoff enforcement;
- bankroll/exposure authority;
- provider acknowledgement and reconciliation;
- emergency kill switch;
- operational monitoring and alerts;
- legal/compliance review;
- explicit manual approval to change governance from
  `real_money_execution=false`.

Automatic execution must never be used as a shortcut around strategic validation.

---

### Betting-product roadmap

The probability object must match the bet product. A Win model does not automatically
produce a valid Place, Quinella, Trifecta or multi-race probability.

Planned order:

1. **Vinner / Win** — current primary research product.
2. **Plass / Place** — build and calibrate a dedicated placing distribution.
3. **Tvilling / Quinella** — model joint finish-order probabilities.
4. **Trippel / Trifecta** — joint order model plus combinatorial ticket economics.
5. **DD / V4 / V64 / V65 / V75 / V85** — multi-leg joint probability, ticket
   construction, pool/dividend model, reserve/scratch logic and system optimization.
6. Cross-provider fixed-odds/exchange comparison only when legal, stable APIs and
   timestamped executable prices are available.

Each product needs its own settlement contract and its own shadow-validation period.

---

### Illustrative 10,000 NOK/month research budget

HBI does **not** currently require 10,000 NOK/month. The current public/read-only stack
is intentionally inexpensive. The following is an example of where a larger research
budget could eventually create value:

| Area | Illustrative monthly allocation | What it should buy |
| --- | ---: | --- |
| Premium data | 2,000–4,000 NOK | deeper historical form, sectionals, trainer/jockey data, weather/going, more countries |
| Infrastructure | 1,000–2,000 NOK | durable database, object storage, scheduled compute, monitoring |
| ML/GPU | 0–2,000 NOK | challenger training/experiments when CPU is no longer sufficient |
| LLM/API | 1,000–2,500 NOK | evidence extraction, research reports, provider/schema assistance |
| Monitoring/maintenance | remainder | provider breakage, data QA, observability, backups and research tooling |

Spend should follow measured bottlenecks. There is no reason to pay for GPU capacity
while data quality is the limiting factor, or to pay for a premium feed unless it
improves full-field coverage, timeliness or research value.

---

### What actually determines whether HBI can make money

No AI system can guarantee that it will beat horse-racing markets.

The market is itself a strong model. Benter explicitly treats public odds as a useful
probability estimate and argues for measuring the fundamental model's incremental
information relative to that public estimate. The practical problem is therefore not
simply "predict the winner".

Long-run viability depends on a chain in which **every link matters**:

```text
better / cleaner data
        +
calibrated independent probabilities
        +
market information
        +
real mispricing
        +
executable price
        +
disciplined staking
        +
sufficient opportunity volume
        +
low operational error
        =
possible durable edge
```

The most likely sources of advantage are:

1. better point-in-time data;
2. better probability calibration;
3. extracting information the market has not fully priced;
4. reacting quickly enough to material changes;
5. avoiding bad or incomplete races;
6. betting only at prices above fair value;
7. controlling stake, liquidity and drawdown;
8. repeating the process across enough races for a small edge to matter.

The project must remain willing to conclude that a feature, model, country, product
or even the whole strategy does **not** provide a durable edge.

---

### Timeline from current V1

The dates below are planning windows, not promises; provider access and the rate at
which untouched eligible races accumulate can move them.

| Window | Main objective | Expected output |
| --- | --- | --- |
| **Now–Oct 2026** | Let V1 operate; harden international full-field data coverage | stable SE/DK collection, provider health, frozen T-4 decisions, settlement evidence |
| **Oct–Dec 2026** | Expand Phase 1 data plane | own chronological horse history, broader trainer/driver/context data, denser market paths |
| **Nov 2026–Jan 2027** | Build feature factory without changing Champion | reproducible feature blocks, ablation harness, richer learning dataset |
| **Dec 2026–Mar 2027** | Develop Challenger candidates | regularized/boosting challengers, calibration research, locked discovery cutoffs |
| **Q1–Q2 2027** | Accumulate untouched Challenger forward evidence | Champion vs Challenger vs Market comparisons across slices |
| **Q1–Q2 2027** | Risk-engine research in parallel | fractional-Kelly/pool-impact/exposure simulations, still shadow-only |
| **2027+ after validation gates** | Expand bet products | Place -> Quinella/Tvilling -> Trifecta/Trippel -> multi-leg products |
| **Only after strategic validation and explicit approval** | Consider execution integration | provider-safe execution sandbox, then possibly tightly controlled real-money mode |

The critical path is currently **data + prospective evidence**, not adding more model
complexity.

`build next step` is evidence-driven: the system audit selects the weakest current critical
chain link and one proximate objective. Calendar dates are planning windows only; they do
not authorize roadmap progression when a harder bottleneck remains open.

---

### Research/source hierarchy behind this roadmap

HBI intentionally distinguishes methodological evidence from product marketing.

**Primary methodology**

- William Benter, *Computer Based Horse Race Handicapping and Wagering Systems*:
  empirical full-field probabilities, holdout/OOS testing, public-market information,
  value, wager sizing, fractional Kelly and pari-mutuel pool impact.
- The project's Benter-first V3/V3.2 architecture and current point-in-time research
  protocol.

**Strategic governance**

- Richard Rumelt, *Good Strategy/Bad Strategy*: used for diagnosis -> guiding policy ->
  proximate objective -> coherent actions, chain-link/bottleneck focus, explicit defer
  choices and create/destroy hypothesis discipline. Rumelt has no authority over
  p(win), fair odds, model weights, staking or claims that racing markets are beatable.
**Supporting model architecture**

- the Ventus horse-racing paper: useful as supporting evidence for separating
  prediction/model output from betting-strategy evaluation and for evaluating returns
  rather than precision alone.

**Secondary betting discipline**

- the project HANDBOOK/Winnermetrics material and betting guides: useful for the
  value/PASS principle, bankroll discipline and the idea that picking winners is not
  the same as making profitable bets. Commercial performance claims are not treated
  as proof.

**Feature inspiration only**

- commercial/consumer descriptions such as
  https://horseracingoracleai.com/blog/build-ai-horse-racing-model and
  https://racehp.ai/horse-racing/, plus other AI-racing product descriptions, are
  useful for identifying candidate data families such as horse form, jockey/trainer,
  weather, going and live market movement. Their advertised feature counts or
  performance claims are **not** promotion evidence for HBI.

Source-derived ideas become part of HBI only after they survive the project's own
point-in-time, out-of-sample and Champion/Challenger validation.

## Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
```

## Non-goals for the first foundation

The repository does **not** currently:

- place real-money bets
- scrape a provider without an explicit/approved integration
- let an LLM directly generate production p(win)
- treat odds shortening as automatic "smart money"
- promote new features because of one profitable backtest

The Rikstoto integration is read-only and intentionally contains no login, account,
purchase or real-money submission code. Historical/inferred endpoints are not part of the live critical path and must fail
closed when their contract is unavailable.

## Research rule

New features or models start as **challengers**. They can influence production only
after point-in-time, untouched out-of-sample evaluation shows incremental value over
the current champion **and the market-only baseline**. Hit rate alone is never a
promotion criterion.


## CLI data flow

A complete local dry run can now be executed without any live provider:

```bash
hbi --db data/hbi.sqlite init-db
hbi --db data/hbi.sqlite import-races examples/races.json
hbi --db data/hbi.sqlite import-snapshots examples/snapshots.json \
  --race-start 2026-09-27T18:00:00+00:00 \
  --source-uri fixture://demo
hbi --db data/hbi.sqlite import-results examples/results.json
hbi --db data/hbi.sqlite export exports/ --format csv
```

When a real provider is connected, it should emit the same canonical objects rather
than changing the modelling/database layer.

### Optional Google Sheets mirror

Install the optional dependency:

```bash
pip install -e ".[sheets]"
```

Then use a Google service-account credential file:

```bash
hbi --db data/hbi.sqlite sync-sheets \
  --spreadsheet-id YOUR_SHEET_ID \
  --credentials /secure/path/service-account.json
```

The mirror writes to new worksheets prefixed with `HBI_` by default. It does not
overwrite an existing manually maintained `RACES`, `SNAPSHOTS` or
`BETS_OUTCOMES` worksheet.

See [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md) for provider format and
[docs/RESEARCH_PROTOCOL.md](docs/RESEARCH_PROTOCOL.md) for model governance.


## GitHub-hosted hourly PRE-WATCH

The repository now includes `.github/workflows/prewatch-hourly.yml`.

After this workflow is merged to the default branch, GitHub Actions schedules the
same operating cadence as the current PRE-WATCH concept:

- 09:00 Europe/Oslo: `MORNING_DISCOVERY`
- hourly from 10:00 through 21:00 Europe/Oslo: `HOURLY_WATCH`

The workflow cron covers both CET and CEST and a Python timezone gate decides whether
the current run belongs in the Oslo watch window.

GitHub-hosted runners are ephemeral, so successful runs upload `data/hbi.sqlite` as
an `hbi-state` artifact. The following run restores the latest state before doing
new work. This gives the first GitHub-native persistent deployment without committing
the binary database to source control.

Until a live racing/market provider is configured, scheduled runs intentionally
finish as audited `NOOP` runs instead of creating fake race data. The scheduler and
persistence are therefore deployable before the provider layer.

See [docs/GITHUB_ACTIONS.md](docs/GITHUB_ACTIONS.md).


## Rikstoto shadow research

The repository now has a GitHub-native paper-betting loop:

```text
Rikstoto raceday discovery
  -> five-minute read-only market watcher
  -> early + best-effort T-4 snapshots
  -> V3.2 market/fundamental check
  -> immutable shadow BET / PASS / NOT_EXECUTABLE
  -> official result/final-odds settlement
  -> 00:30 Europe/Oslo daily review
```

The five-minute watcher runs through 23:59 Europe/Oslo so late races are not lost.
Every HBI workflow that writes the persistent SQLite artifact uses the shared
`hbi-state-writer` concurrency group, preventing two runs from restoring the same
old database and overwriting each other.

Automatic paper decisions currently start with **Vinner**. Rikstoto `/starts` is the
canonical live field. HBI then probes approved read-only enrichment providers. ATG is
currently live-verified for complete Swedish and Danish fields. A race is admitted only
when every active runner is safely matched and has the complete market-free history
contract before creating the frozen `FUNDAMENTAL_CHAMPION_V1_1` p(win) distribution.

V1.1 is a **shadow Champion**, not a validated production model. It requires at least
80% known history coverage before the betting layer may simulate a ticket. Norwegian
races are still captured automatically, but without a verified pre-race history source
they correctly remain `CAUTION / NOT_EXECUTABLE` rather than receiving invented
history. Plass, Tvilling and Trippel market data remain observational only.

See [docs/RIKSTOTO_PROVIDER.md](docs/RIKSTOTO_PROVIDER.md) for endpoint provenance and
[docs/SHADOW_BETTING.md](docs/SHADOW_BETTING.md) for decision/settlement rules.


See [docs/FUNDAMENTAL_CHAMPION_V1.md](docs/FUNDAMENTAL_CHAMPION_V1.md) for the exact
market-free formula, point-in-time rules and promotion gate.


## Research Observatory

The Shadow Champion remains frozen while the repository accumulates prospective data.
At 00:30 Europe/Oslo, after settlement, HBI now builds a separate Research Observatory
report covering data health, T-4 timing, provider failures, fundamental/market/combined
log loss and Brier, calibration, model-market conflict, CLV and paper P/L.

Every first T-4 decision is frozen in `shadow_decision_runs`, including PASS and
NOT_EXECUTABLE races, so later evaluation is not limited to the bets that happened to
be placed.

The nightly workflow also creates a unique research backup containing SQLite, CSV,
JSON and SHA-256 manifest files with requested 90-day artifact retention.

See [docs/RESEARCH_OBSERVATORY.md](docs/RESEARCH_OBSERVATORY.md).


## V1 completion semantics

HBI V1 separates **engineering completion** from **strategic validation**. The platform
can be engineering-complete while the strategy remains NOT_VALIDATED and continues to
accumulate prospective shadow evidence.

The static machine-readable policy authority is
`docs/research_governance.json`. The latest real-state V1 audit derives
`research-v1/research-status.json`, which is the current evidence view of P0
integrity. See `docs/RESEARCH_GOVERNANCE.md`, `docs/RESEARCH_STATUS.md` and
`docs/V1_ACCEPTANCE_CRITERIA.md`.

A new Challenger never inherits the sample that was used to discover it. Each
Challenger receives its own prospective forward-validation clock.

International ingestion: see [FULL_FIELD_ONLY provider capabilities](docs/INTERNATIONAL_FUNDAMENTALS.md).

October progress: [evidence-driven tracker and dashboard](docs/OCTOBER_TRACKER.md),
generated daily from production state with country filters, milestone blockers,
paired model scores and verified-price paper results.

## PRE-WINNER bulk research

[PRE-WINNER Engine v1.0](docs/PRE_WINNER_ENGINE_V1.md) processes weekly crawler PRE archives into one frozen upload ZIP, with exclusive signal tiers, timing cohorts, QC and hashes.
