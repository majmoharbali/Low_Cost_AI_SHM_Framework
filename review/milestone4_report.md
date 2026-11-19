# Milestone 4 · KW51 sensor reduction and signal degradation

The engineered two-channel layout reproduced the full-deck change flags on all 18 commonly scorable held-out recordings. Some random layouts matched it, while others missed most of the full-deck post-retrofit flags despite having four channels. Channel placement mattered in this pilot. The two-channel result applies to the selected mode panel and these records.

## Synchronous recordings and identification check

The [prespecified protocol](milestone4_protocol.md) sampled 62 UTC hours across April and July 2019 and January 2020. Individual members of the official monthly ZIPs were fetched by byte range, reducing the download from several full archives to about 802 MB of extracted MATLAB files. The [manifest](kw51_raw_pilot_manifest.csv) records each ZIP member's CRC, size and SHA-256. The checks bind individual records. A full-archive MD5 cannot be checked from selected ranges. Cite the [dataset](https://doi.org/10.5281/zenodo.3745914) and [Maes and Lombaert data paper](https://ascelibrary.com/doi/10.1061/%28ASCE%29BE.1943-5592.0001668) when using the benchmark. [Benchmark terms](https://bwk.kuleuven.be/bwm/kw51).

The files supply synchronously sampled, provider-preprocessed time series. The loader checked the common `predat_a.sdn` clock at 825.806 Hz, its alignment with the timestamp in each filename, acceleration in m/s² as documented by the provider, and the six labelled deck columns. It downsampled by 16 with an anti-alias filter and used equal 120-second crops. The 2,048-point Welch segments give a 0.0252 Hz spectral bin at the study rate. The pilot design used the six-channel quality mask for all layouts. Three calibration hours and four reference-test hours had an incomplete six-channel crop, so they count as abstentions even for layouts that might have operated on some surviving channels.

| Provider mode | Development full-deck FDD found / usable | Same-hour SSI pairs within two bins / available pairs |
|---|---:|---:|
| 3 | 20 / 20 | 20 / 20 |
| 5 | 19 / 20 | 18 / 18 |
| 6 | 20 / 20 | 20 / 20 |
| 9 | 20 / 20 | 20 / 20 |
| 13 | 20 / 20 | 20 / 20 |

All five modes passed the development check. The rule chose modes 3 and 6 for the score. The comparison with an hourly provider estimate checks agreement within a band at a nominal hour. It does not establish simultaneous estimates from identical excerpts or independent mode truth. The same non-overlapping bands and FDD quality checks then ran on every layout and condition.

## Reduced layouts on held-out recordings

The engineered four-channel layout used `aBD11Az`, `aBD17Ay`, `aBD23Ay` and `aBD23Az`. The engineered pair used `aBD17Ay` and `aBD23Az`, preserving both lateral and vertical response. Layouts were frozen on development shapes. Each clean layout calibrated its score on separate reference dates. The full deck and engineered layouts had 20 complete development hours and 17 calibration hours. With 17 calibration observations the 99th-percentile cutoff is the maximum calibration score, a descriptive cutoff with little tail resolution.

| Clean layout | Reference flags / scored (10 scheduled) | Retrofit flags / scored (6 scheduled) | Post-retrofit flags / scored (6 scheduled) | Disagreements / pairs vs. full deck | Lost estimates vs. full deck, all five bands |
|---|---:|---:|---:|---:|---:|
| Full six | 0 / 6 | 3 / 6 | 6 / 6 | 0 / 18 | 0 |
| Engineered four | 0 / 6 | 3 / 6 | 6 / 6 | 0 / 18 | 0 |
| Random four 1 | 0 / 5 | 1 / 6 | 1 / 6 | 7 / 17 | 2 |
| Random four 2 | 0 / 6 | 3 / 6 | 6 / 6 | 0 / 18 | 2 |
| Random four 3 | 0 / 6 | 3 / 6 | 6 / 6 | 0 / 18 | 0 |
| Engineered two | 0 / 6 | 3 / 6 | 6 / 6 | 0 / 18 | 1 |
| Random two 1 | 0 / 6 | 3 / 6 | 6 / 6 | 0 / 18 | 0 |
| Random two 2 | 0 / 6 | 3 / 6 | 4 / 4 | 0 / 16 | 5 |
| Random two 3 | 0 / 5 | 1 / 6 | 1 / 6 | 7 / 17 | 3 |

Across five bands and 18 usable held-out records, the full deck identified 79 of 90 possible estimates. The engineered four retained all 79 with frequencies within one bin. The engineered two retained 78, with 76 within one bin and the one lost estimate in mode 9. Random four 1 and random two 3 agreed within one bin in only 7/17 and 8/17 valid mode-6 pairs. Both omit `aBD23Az` and `aBD11Az`. Their dropout and frequency disagreements explain why availability and identification need to be considered with the flag comparisons. Pairwise mode-shape agreement is measured after projecting onto shared channels and is interpreted only where both estimates exist. It does not establish recovery of a complete shape from two channels.

## Input degradation

The pilot reran FDD after adding noise, DC offsets, relative timing delays or burst gaps to copies of the measured series. A 5 dB nominal ratio to total measured RMS represents added noise, with original sensor noise still present. The archive acceleration signals are already preprocessed. Pure offsets are a control because segment detrending removes their mean, and this case does not represent saturation or drift. Gaps are passed to the existing quality checks as missing samples.

Five of the 18 otherwise scorable held-out crops were hit by the scheduled burst. Both layouts abstained on all five and matched their clean flags on the remaining 13. The engineered pair lost three of the full-deck modal estimates under added noise, versus one in its clean run. Its two scoring modes kept all 18 scores and retained agreement in change flags at the tested noise level.

| Input condition | Full six scorable / flag disagreements vs. clean full | Engineered two scorable / flag disagreements vs. clean full | Full six / engineered two lost estimates vs. clean full |
|---|---:|---:|---:|
| Added noise | 18 / 0 | 18 / 0 | 0 / 3 |
| DC bias | 18 / 0 | 18 / 0 | 0 / 1 |
| Relative delay | 18 / 0 | 18 / 0 | 0 / 1 |
| Burst gaps | 13 / 0 | 13 / 0 | 22 / 23 |

The initial timing implementation accidentally assigned the engineered pair equal delays. The corrected test distributes zero to three sample delays across each layout, giving up to 58.1 ms of relative skew, and the replay was repeated. Change flags remained stable, but relative phase was affected. For post-retrofit mode 13, median shape agreement with the clean full-deck estimate dropped from 1.00 to 0.62 in the six-channel case. The engineered pair's agreement on its shared channels dropped from 1.00 to 0.83. This is an effect on measured shape components at the tested delay.

The corrected run's clean median identification times across the three held-out periods ranged from 52 to 57 ms for six channels, 30 to 38 ms for four and 9 to 10 ms for two. Timing varied between runs on this host and the cases ran sequentially. Treat these values as indicative computational cost for FDD, with no inference about field power consumption or real-time deployment.

## Reproduce

From the repository root, use the pinned project environment and the Milestone 2 archive.

```powershell
.venv/Scripts/python.exe -X utf8 -m src.kw51_fetch_raw data/kw51/raw/pilot --workers 4
.venv/Scripts/python.exe -X utf8 -m src.kw51_sensor_pilot data/kw51/raw/pilot/manifest.json data/kw51/zenodo-3745914/trackedmodes.zip --output outputs/kw51_m4/pilot.json
```

The CLI produces layout and model configurations, per-period availability, flag agreement, modal pairing, frequency differences, shape agreement, abstention reasons and runtime. Use a fresh output path for a repeat. Timings describe FDD and its quality checks on this machine, excluding per-record parsing, resampling and downloads. The CSV provides file identity for the selected recordings. The recording and replay directories are ignored by Git.

The input JSON manifest SHA-256 was `d178cac66738e8231d51230c2970cbf19a0929908ff7fdeb1ad7a4bbb937059b`. The corrected output SHA-256 was `4e88b08009db0b5f6680a96d9de31d06c6854e7b28984067cd06e6d14a612799`. Every non-timing scenario gave identical scientific results across the initial and corrected runs, excluding wall-clock measurements. The local suite passed 43 tests, including loopback. The four raw-pilot tests passed again after the timing correction.

This is a sparse pilot with one bridge, a short reference calibration and one preprocessed raw-signal source. The results support testing a smaller candidate layout against a reference instrument. They leave open the minimum sensor count across environmental and operating conditions, physical low-cost sensor performance, and whether the shift is attributable to retrofit alone.
