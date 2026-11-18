# Milestone 3 · Environmental baselines on KW51

Temperature compensation did not reduce persisted alarms in the held-out reference period. All three models produced one episode. They all exceeded their thresholds on every commonly scorable post-retrofit hour, indicating a shift relative to the pre-retrofit reference. The archive's changes in instrumentation, missing modes and provider tracking constrain the interpretation of this shift.

The inputs are the [KW51 v1.0 published modal features](https://zenodo.org/records/3745914) from [Milestone 2](milestone2_kw51.md). The [analysis protocol](milestone3_protocol.md) was committed before fitting or scoring later periods. This is a chronological replay of precomputed features from one bridge. The months before the retrofit constitute the reference condition, which may already contain defects. [Benchmark description](https://bwk.kuleuven.be/bwm/kw51) · [Maes and Lombaert data paper](https://ascelibrary.com/doi/10.1061/%28ASCE%29BE.1943-5592.0001668).

## Schedule and calibration

| Block | First to last included hour, archive clock | Scheduled hours | Common rows used |
|---|---|---:|---:|
| Fit | 2018-10-01 00:00 to 2019-02-12 13:00 | 3,230 | 2,791 |
| Calibration | 2019-02-13 14:00 to 2019-03-29 18:00 | 1,061 | 998 |
| Reference test | 2019-03-30 19:00 to 2019-05-14 23:00 | 1,085 | 996 |
| Retrofit | 2019-05-16 00:00 to 2019-09-26 23:00 | 3,216 | 1,793 |
| Post-retrofit | 2019-09-28 00:00 to 2020-01-15 23:00 | 2,640 | 1,622 |

The two 24-hour purges precede calibration and reference testing. The two retrofit boundary dates remain excluded. Modes **3, 5, 6, 9 and 13** met the 90% fitting-block joint coverage requirement with Vliet air temperature. Their individual fitting coverage ranged from 90.1% to 93.7%. All three primary models use the same complete fitting rows and common calibration hours. Allowed air-temperature support was **−7.53 to 25.86 °C** based on the complete fitting data.

The spline selected penalty **1.0**, the strongest tested value, in the expanding-window validation on fitting data. The three folds retained 590, 624 and 546 supported validation hours, respectively. The chosen penalty had the lowest mean standardised squared error among the four prespecified candidates. It was retained at the grid boundary. The constant, linear and spline squared residual score cutoffs were **18.599**, **22.199** and **21.639**, respectively. These are empirical calibration quantiles, with each score in its own fitted residual covariance scale.

## Primary comparison on common supported hours

| Period | Model | Hours scored / scheduled | Exceeding hours | Persisted alarm hours (% of scored) | Episodes | Episodes / 30 scheduled days |
|---|---|---:|---:|---:|---:|---:|
| Reference test | Constant | 996 / 1,085 | 10 | 1 (0.10%) | 1 | 0.66 |
| | Linear | 996 / 1,085 | 9 | 1 (0.10%) | 1 | 0.66 |
| | Spline | 996 / 1,085 | 9 | 1 (0.10%) | 1 | 0.66 |
| Retrofit | Constant | 1,793 / 3,216 | 1,762 | 1,211 (67.5%) | 327 | 73.21 |
| | Linear | 1,793 / 3,216 | 1,758 | 1,207 (67.3%) | 328 | 73.43 |
| | Spline | 1,793 / 3,216 | 1,759 | 1,207 (67.3%) | 328 | 73.43 |
| Post-retrofit | Constant | 1,622 / 2,640 | 1,622 | 1,185 (73.1%) | 298 | 81.27 |
| | Linear | 1,622 / 2,640 | 1,622 | 1,185 (73.1%) | 298 | 81.27 |
| | Spline | 1,622 / 2,640 | 1,622 | 1,185 (73.1%) | 298 | 81.27 |

Common coverage was **91.8%** in reference testing, **55.8%** during the retrofit and **61.4%** afterwards. A persisted alarm occupied 0.09% of all scheduled reference test hours, 37.5–37.7% of scheduled retrofit hours and 44.9% of scheduled post-retrofit hours. The reference result has only one episode per model. The seven-day moving-block bootstrap gave descriptive 95% intervals of 0–1.99 episodes per 30 days for the constant model and 0–0.66 for each compensated model. The paired compensation-minus-constant intervals were −1.99 to 0 for both, with an observed difference of zero. These sparse-event intervals depend on where a single episode falls within a short test record and do not establish improved persistence. Fit-only air-temperature autocorrelation was 0.81 at 24 hours and 0.30 at 168 hours. Dependence remains despite the purges.

On its operating eligibility, the constant model scored an additional 173 hours during the retrofit and 24 afterwards. Its corresponding operating episode counts were 359 and 301. Temperature-conditioned operating counts equal the common counts. The complete panel was missing in 89, 1,250 and 994 scheduled hours respectively across the three evaluation periods. During the retrofit, 274 scheduled hours were outside fitting temperature support, including 168 with the complete panel. Another five retrofit hours lacked air temperature. The post-retrofit period had 53 hours without air temperature and none outside its range. The generated JSON reports overlapping reason counts and per-model abstentions.

Every commonly scored post-retrofit hour exceeded the threshold. The 298 episodes mainly reflect persistence resetting at interruptions. They measure this operating rule's behaviour and do not identify independent changes or damage events. No onset-based detection delay is identifiable. The addition of six arch channels and the use of the provider's across-campaign tracking preclude separating structural and upstream measurement effects in this replay.

## Temperature proxy check

The secondary linear comparison retained 1,821 paired fitting and 904 jointly supported calibration hours. On 683 common reference test hours, both Vliet air and on-site surface temperature yielded four exceedances and zero persisted episodes. During retrofit, the two models produced 30 and 28 episodes respectively among only 152 jointly supported hours. Post-retrofit, both produced 254 episodes among 1,388 shared hours and exceeded on all of them. The paired fitting sample narrows temperature support, and these comparisons use different denominators and thresholds from the primary run. The small reference episode counts do not distinguish the proxies.

## Reproduce and inspect

Use the [archive manifest](kw51_manifest.json) and the project Python environment. Choose a fresh output directory for each run. The first command writes the fitted parameters and thresholds. The second reads that artifact, scores held-out periods and records its SHA-256 in the output:

```powershell
.venv/Scripts/python.exe -X utf8 -m src.kw51_replay freeze data/kw51/zenodo-3745914/trackedmodes.zip --frozen outputs/replay/frozen.json
.venv/Scripts/python.exe -X utf8 -m src.kw51_replay evaluate data/kw51/zenodo-3745914/trackedmodes.zip --frozen outputs/replay/frozen.json --output outputs/replay/evaluation.json
```

Two runs on Windows, Python 3.13.7, produced byte-identical artifacts:

- Frozen JSON SHA-256 `aeb6c23d7ae2b02925a43c95579a9d1df6eb542911dbc005cfb8599599441922`
- Evaluation JSON SHA-256 `503d97e55a18de1f2836a5d507fae5494f90974f7c92ee68cae6c5a86c62ec03`

Floating-point output can vary across platforms and library builds. All 39 tests passed locally. New tests verify disjoint time blocks, invariance of the freeze to held-out mutations, separate threshold calibration, support abstention and persistence across missing and non-adjacent hours. The underlying archive and generated fitted artifacts remain in ignored local directories.

For this replay the constant reference offers comparable held-out persistence with fewer inputs. The next experimental gate is a fixed synchronous raw sensor configuration and verified identification on real recordings, as specified for Milestone 4.
