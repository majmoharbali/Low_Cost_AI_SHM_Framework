# Milestone 1 evidence report

Reviewed baseline: `39ca47f6b7627c326f26d953307c3af16a2ef962`. Work is on `research/baseline-foundation`. This report concerns numerical verification and reproducible software execution; no measured-data modelling has started.

## Implemented behaviour

The numerical research path uses a consistent-mass Euler–Bernoulli beam with mass-normalised modal reduction, SI acceleration and exact zero-order-hold state propagation. The legacy classifier is isolated behind explicit launch flags and a source/checksum boundary. It is used only at its original sensor-0 location. The legacy display starts without observations and issues no global health probability or causal SHAP explanation. Original resource and fusion modules remain historical snapshots, outside the runnable research path.

Shared SignalWindow and DetectionResult interfaces preserve provenance, units and validity. Missing, invalid, future or stale required records yield no modal estimate or detector score. Welch/FDD uses synchronous cross spectra and explicit search bands. It does not provide a damping estimator, damage classifier or independent validation of a real structure.

## Numerical results

| Quantity | Result |
|---|---|
| First three FE frequencies | 1.963496, 7.854035, 17.672060 Hz |
| Largest analytical frequency error | 0.003403%, below the 0.1% acceptance tolerance |
| Uniform 60% stiffness-loss frequency-ratio error | 2.07e-10 absolute against sqrt(0.4) |
| ZOH 100 versus 200 Hz acceleration difference | 3.89e-16 m/s² for the same piecewise-constant force |
| Controlled FDD frequency estimates | 1.953125, 7.861328, 17.675781 Hz |
| Spectral bin spacing | 0.024414 Hz; each controlled estimate is within one bin |
| MAC against known sensor shapes | 0.999987, 0.997523, 0.987145 |
| Second mode at the midspan-only sensor | Unavailable, as required by its modal node |
| Short random excitation, seed 7 | First mode identified; modes 2 and 3 ambiguous and omitted |
| Detector score and threshold | Absent: no detector fitted |

Controlled FDD uses periodic nodal pulses and model-informed search bands. Prescribed harmonic mixtures additionally verify cross-spectral shape recovery. These checks establish implementation correctness under specified numerical conditions, not field performance. The short random-record result is retained as a failure case rather than tuned into a successful estimate.

`milestone1_results.json` records configurations, numerical outputs, source hashes and the pre-finalisation source revision. Its working-tree flag is true because the experiment was run before the third commit; hashes identify the tested files. Regenerate a clean-revision result with `python -m src.verify_mechanics` after checkout.

## Execution and limits

Local environment: Windows 11, CPython 3.13.7, isolated virtual environment. Pinned direct dependencies and resolved package versions are supplied. All 30 tests pass, including a real loopback WebSocket replay and finite shutdown. The complete suite was run outside the network-restricted sandbox so loopback connections could be exercised. Package consistency, public launcher help/opt-in checks, finite legacy inference and finite synthetic-training smoke commands pass. The original model checksum remains `e7bd995ab8edc69656b8bf221da0de5c85b120476be112189368dbefd2801745`.

Dashboard inline JavaScript passes Node syntax checking. A browser rendering check was attempted but the in-app browser could not reach the local loopback server; visual browser behaviour is not claimed verified. The real WebSocket replay has a separate integration test. CI is configured for Windows and Ubuntu with Python 3.13; remote outcomes must be checked after push rather than inferred from local execution.

Graphify outputs are local under `graphify-out/`, ignored by Git. The graph is an aid to navigation; extraction health diagnostics, missing external endpoints and edge-collapse warnings are retained in its report. Semantic host-agent token usage is unavailable from the tool and is not represented as measured zero cost.

## Next gate

Review these numerical results before measured-data modelling. Next obtain/audit official Z24 records or the KW51 modal archive, freeze the reference/intervention chronology and partitions, then fit environmental baselines. No Z24 request, data download, hardware experiment, damage probability or structural safety assessment is included in this milestone. See `study_protocol.md` for the remaining stages and acceptance gates.
