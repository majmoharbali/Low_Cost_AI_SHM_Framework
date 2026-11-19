# KW51 deck replay dashboard

The dashboard compares the six original deck channels with the retained pair, `aBD17Ay` and `aBD23Az`. Both layouts use the original field recordings. The simulated input conditions change copies of those recordings before modal identification. The dashboard compares frequency-based change flags and unavailable results for the selected acquisition. See the [pilot protocol](milestone4_protocol.md) and [pilot report](milestone4_report.md) for the scoring rule and limitations.

From the project root, with the pilot recordings and modal archive already in place, generate a new local report and portable dashboard. Put Poppler's `pdftoppm` on PATH and adjust `..\blueprints` if the supplied drawings are stored elsewhere.

```powershell
$run = 'outputs/kw51_dashboard_' + (Get-Date -Format 'yyyyMMdd_HHmmss')
.\.venv\Scripts\python.exe -m src.kw51_sensor_pilot data/kw51/raw/pilot/manifest.json data/kw51/zenodo-3745914/trackedmodes.zip --acquisitions --output "$run/pilot.json"
.\.venv\Scripts\python.exe -m src.kw51_dashboard "$run/pilot.json" ..\blueprints --output "$run/index.html"
Invoke-Item "$run/index.html"
```

Open the generated `index.html` in a browser. It contains the plotting data and drawing crops and works offline. Click a station to identify the channels and select a scheduled hour to compare the modal estimates and change flags. The original-recordings view gives 18 of 22 held-out hours scorable in both layouts, 18 of 18 matching change decisions, and 78 of 79 full-deck modal estimates also found by the pair. Those counts use the full deck under the selected input condition as the mode availability denominator. Changing the input filter compares the two layouts under that same condition.

The map uses the plan from `Other/overview.pdf`; the expandable source panel shows a plan detail from drawing KW51-01A. The four marker locations correspond to six channels. Girder and longitudinal positions come from `Other/select_sensors.m` and the bearing coordinates from `Other/model_kw51.m`. The image registration is approximate. The generated file records SHA-256 hashes for the drawings, replay report and recording manifest.

The exported dashboard embeds derived data and drawing images. Keep it local unless sharing under the benchmark terms, with the attribution and licence for those materials. The [KU Leuven benchmark page](https://bwk.kuleuven.be/bwm/kw51) provides dataset, drawing and model credits and the CC BY-NC-SA 4.0 terms.
