# Low-cost SHM: research baseline and legacy demonstration

This repository is being rebuilt around one question: **how well can environmental effects be separated from structural changes in measured vibration data, and how does performance deteriorate with fewer sensors or poorer measurements?**

Milestone 1 provides a numerical verification foundation. It does not establish measured-data damage detection, structural safety, low-cost hardware performance, battery life or deployment suitability in Sudan. The earlier classifier and dashboard remain a labelled legacy synthetic demonstration.

## Installation

Use Python 3.13 and a project-local virtual environment:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m src.verify_mechanics --output outputs/verification.json
```

On Linux use `.venv/bin/python`. CI runs numerical and smoke checks on Windows and Linux. Dependency versions are pinned; the tested resolved environment is recorded in `review/environment-freeze.txt`.

## Numerical research path

The reference is a simply supported Euler–Bernoulli beam: 20 m span, 0.30 by 0.50 m section, E = 30 GPa, density 2,500 kg/m³, and 20 consistent-mass finite elements. Its three retained mass-normalised modes have 2% damping. Inputs are nodal forces in newtons held constant between samples; outputs are acceleration in m/s². Independent sensor noise is added after the response. There is no per-window amplitude normalisation.

The reduced model verifies numerical methods. It is not a calibrated model of Z24, KW51 or a field asset. It omits shear deformation, rotary inertia and response from truncated higher modes. Plain FDD estimates frequencies and relative mode shapes, not damping. Missing or ambiguous modes are unavailable. No research detector has been fitted: scores and thresholds remain absent.

## Legacy demonstration

The original artifact is preserved with its checksum and source revision in `review/legacy_manifest.json`. Original runtime, fusion, explanation and resource models are retained under `src/legacy/` for historical inspection. Moving them does not repair their scientific limitations.

The public launchers require explicit opt-in:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-legacy.txt
.venv/Scripts/python.exe -m src.main_simulation --legacy --smoke
.venv/Scripts/python.exe -m src.main_simulation --legacy --windows 6
.venv/Scripts/python.exe -m src.train_model --legacy --smoke
```

Open `dashboard/index.html` for the finite legacy stream. Only sensor 0 is classified, matching the original training location. Other channels are displayed without classification. The interface issues no global structural-health assessment. Retraining writes to `outputs/legacy/`, never over the original artifact. The reproduction retains the old in-sample evaluation limitations; synthetic classes are not engineering severity definitions.

The research modules never load the saved classifier. Its legacy loader verifies the original checksum and rejects non-legacy source identifiers before loading or prediction.

## Measured-data milestones

1. Obtain and audit official Z24 recordings, or use the small KW51 tracked-modal-results archive if Z24 access remains pending.
2. Freeze chronology, exclusions and time-group partitions before comparing constant, linear-temperature and spline-temperature reference models.
3. Calibrate thresholds on separate reference records; evaluate held-out reference alarms, intervention responses, availability and abstentions.
4. Study sensor reduction only with synchronous raw recordings. Processed modal results cannot establish reduced-sensor performance.

Z24 requires [official registration](https://bwk.kuleuven.be/bwm/z24/registration); its recordings must not be redistributed. [KW51](https://bwk.kuleuven.be/bwm/kw51) has an [official archive](https://zenodo.org/records/3745914). Its reference condition may contain existing defects; retrofit-associated change is not a known damage-onset label. Neither dataset has been analysed by this milestone.

Local recordings, generated outputs and `graphify-out/` are ignored. The graph supplements source inspection and reports extraction-integrity warnings. The detailed protocol and milestone evidence are in `review/`.

Author: Majzoob Ali. Low-cost sensing remains a later experiment requiring reference-instrument comparison and measured operation profiles.
