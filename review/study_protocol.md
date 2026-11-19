# Study protocol and implementation gates

## Question and present evidence

How well can environmental effects be separated from structural changes in measured vibration data, and how does performance deteriorate with fewer sensors or poorer measurements?

Milestone 1 verifies a specified numerical beam and signal-processing functions. It has no measured-data detector, calibrated damage probability, capacity model or hardware validation. The legacy classifier is quarantined and retains its historical in-sample evaluation limitations. Numerical verification and experimental validation are separate evidence requirements.

## Milestone 1: verification foundation

The three changes cover reproducible launchers and legacy isolation; consistent-mass beam mechanics; and signal provenance, availability, Welch/FDD identification and this evidence package. The beam uses SI units, mass-normalised retained modes, explicit nodal forces, exact zero-order-hold propagation and separately seeded measurement noise. Forces are sampled loads in N, not a continuous white-noise intensity. Reduction to three modes omits higher-mode response. Geometry is illustrative and not fitted to a benchmark.

SignalWindow stores channel-by-time acceleration, sampling rate, channel IDs, acquisition start time with timezone, units, source, window ID and per-channel quality. Valid timestamps do not prove physical synchronisation; dataset loaders must establish that separately. Non-finite, missing or stale required data cannot produce a frequency or detector score. DetectionResult remains not_fitted after availability checks; there is no default healthy state.

FDD uses a Hann-windowed Welch cross-spectral matrix, 50% overlap and singular value decomposition. The default segment length is 4096 samples. Search bands are explicit, non-overlapping inputs. For numerical checks they come from known eigenfrequencies; measured-data bands must be fixed using reference development records, not intervention outcomes. The peak requires 10% relative prominence and band power at least 0.0001 of the global spectral maximum. Competing peaks at least 80% as strong lead to ambiguity. These are configurable verification QC settings, not calibrated confidence levels. Boundary peaks and insufficient records are unavailable. The first version handles isolated peaks in supplied bands; it does not solve close/repeated-mode identification, autonomous mode tracking, EFDD damping or SSI.

Controlled periodic pulses and prescribed harmonic mixtures verify known-frequency recovery within one frequency bin. Seeded finite random excitation additionally demonstrates that spectral variability can cause abstention. Recovery on the controlled tests does not prove ambient field performance. Missing channels require an explicitly new sensor subset and its own identification configuration; they are not silently dropped from the full setup.

## Milestone 2: measured-data inventory

Use the [official Z24 procedure](https://bwk.kuleuven.be/bwm/z24) if access is available. Otherwise begin with [KW51 tracked modal results](https://zenodo.org/records/3745914), readme and supplied plotting functions, without downloading the full collection. No application or external message is sent as part of milestone 1.

Record archive checksums, origin, dataset version, timestamps/time convention, sessions, units, sampling rates, sensor positions/directions, setup membership, available environment variables and quality exclusions. Inspect actual formats before writing parsers. Preserve raw inputs. Keep Z24 long-term and progressive-damage campaigns separate; do not concatenate sequential setups as synchronous channels. Never pool Z24 and KW51 into one training set. Z24 redistribution is restricted. Check the KW51 licence and cite the dataset and source paper before sharing derived material.

Freeze a documented chronology and reference/intervention/exclusion table before modelling. For KW51, pre-retrofit is a reference condition that may contain defects; retrofit-associated changes are not independently labelled damage onset. If metadata cannot establish an eligible reference period or usable environmental data, stop model fitting and report the missing evidence.

## Milestone 3: environment-conditioned reference detector

Compare an unconditioned frequency reference, linear temperature compensation and a regularised spline temperature model. Select usable modes and environmental inputs using reference development records only. Use residual scores; do not label scores or tail areas as damage probabilities.

Primary prospective replay partitions eligible pre-intervention acquisitions chronologically: 60% fitting, 20% threshold calibration, 20% reference test. Keep acquisitions and overlapping segments together. Remove overlap across partitions; document any additional time gaps using reference autocorrelation and acquisition cadence before evaluating intervention outcomes. Model settings, missing-data treatment, modal matching and residual covariance are learned inside fitting data. No future temperatures, intervention IDs or time encodings of damage are model inputs.

Fix the empirical 99th-percentile calibration threshold and two-consecutive-valid-acquisition persistence rule before the final tests. This does not guarantee a 1% future alarm rate. Missing acquisitions reset persistence; report unsupported environmental conditions as extrapolation. Initially freeze the model during replay; online adaptation requires a separate protocol.

Report reference alarm fractions and episodes per monitored time, intervention-specific outcomes, identification availability, abstentions and environmental support. Report delay only when documented onset supports it. Account for missing/abstained records in denominators. Resample sessions or justified time blocks for uncertainty; windows and folds are not independent damage events or independent bridges. A retrospective seasonal-coverage analysis, if added, must be separate from prospective results. Do not require a complex model to outperform a simple baseline as a condition for honest reporting.

## Milestone 4 and later extensions

With synchronous raw recordings and verified identification, compare engineering-selected and seeded random subsets. Select using development data and rerun identification for each subset. Processed KW51 modal series alone cannot test physical channel reduction. Inject controlled noise, bias, timing errors and burst loss into signal copies before identification. Record that original sensor noise remains present. Report unobservable modes, changes in detection and abstentions rather than promising a minimum channel count.

Physical low-cost sensing, mounting and synchronisation need reference-instrument comparisons. Battery/network claims need measured operation profiles and accounting for loss before the component being tested. Defer FE updating, PINNs, deep models, SHAP, automatic damage localisation and financial-risk optimisation until a measured baseline exposes a specific need. Sudan-specific deployment suitability remains untested.
