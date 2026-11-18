# Milestone 2 · KW51 measured-data audit

The KW51 v1.0 archive supports an environmental reference experiment on published hourly modal features. The comparison can describe changes around the retrofit and test how temperature compensation affects reference alarms. An observed difference can also reflect changes in instrumentation or identification. The sensor reduction experiment needs synchronous raw vibration records.

## From the foundation to measured data

The starting revision is `9a1409d033def90453ec2c4d76274dc19174e0f4`, the head of [draft PR #1](https://github.com/majmoharbali/Low_Cost_AI_SHM_Framework/pull/1). [The Windows and Ubuntu workflow passed](https://github.com/majmoharbali/Low_Cost_AI_SHM_Framework/actions/runs/42327130128). The reference beam's first three frequencies agree with the analytical model to a maximum error of 0.003403%. The controlled FDD estimates are within one spectral bin. These checks establish the numerical foundation.

[KU Leuven's Z24 access procedure](https://bwk.kuleuven.be/bwm/z24#obtaining-the-data) requires registration and restricts transfer of recordings. No local Z24 recording set was found, so this milestone uses the agreed KW51 fallback. A future Z24 audit must keep long-term monitoring separate from the nine sequential progressive-damage setups and identify synchronous channels within each setup.

## Source and format

Kristof Maes and Geert Lombaert's [Zenodo v1.0 record](https://zenodo.org/records/3745914) supplies the 12.9 MB `trackedmodes.zip`, readme and MATLAB plotting functions. All three files match the published MD5 checksums. [The manifest](kw51_manifest.json) records exact download URLs, sizes, local SHA-256 values and the hash of the MATLAB member. The local files are under the ignored `data/kw51/zenodo-3745914/` directory. KU Leuven lists the benchmark terms as CC BY-NC-SA 4.0. Cite both the [dataset](https://doi.org/10.5281/zenodo.3745914) and the [data paper](https://ascelibrary.com/doi/10.1061/%28ASCE%29BE.1943-5592.0001668). The raw ambient and train passage releases are outside the scope of this audit. [KU Leuven benchmark and terms](https://bwk.kuleuven.be/bwm/kw51).

The archive contains one MATLAB Level 5 file with the scalar `modes` struct. The importer checks archive identity, axes, exact column labels and row alignment. The supplied `plot_trackedmodes.m` establishes that `f` is in Hz and that `env` columns 1 and 3 are bridge surface and external air temperature in °C. The data paper describes the other environment labels and the author-supplied hourly SSI and tracking procedure.

| Field | Observed shape | Interpretation |
|---|---:|---|
| `sdn` | 11,328 × 1 | MATLAB serial day numbers, converted to hours without shifting the archive clock |
| `f` | 11,328 × 14 | Natural frequencies in Hz, with mode IDs 1–14 in the supplied order |
| `xi` | 11,328 × 14 | Published modal damping values, preserved as supplied and excluded from the baseline |
| `m` | 11,328 × 14 × 12 | Complex relative mode-shape components at labelled acceleration channels |
| `env` | 11,328 × 11 | Hourly environmental values aligned by archive row |
| `labels_m`, `labels_env` | 12, 11 labels | Channel and environment order, verified by the parser |

Accelerometer IDs with `aBD` are deck positions with lateral (`y`) or vertical (`z`) directions. The `aAR` labels are lateral arch channels. The paper reports that the SSI preprocessing resampled acceleration at 41.3 Hz. The hourly modal output has no raw sampling timestamps, segment boundaries or per-window waveforms. Its time labels identify hourly slots. We preserve them as archive-clock hours and do not infer a new timezone from the serial number format. The data paper specifies UTC for the released ambient files, and the supplying MATLAB modal plot uses the serial hours directly.

## Frozen chronology and exclusions

The archive covers 1 October 2018 00:00 through 15 January 2020 23:00 on its hourly grid. All hours are unique and consecutive. The provider documents a retrofit from 15 May to 27 September 2019. The supplied plotting script marks both dates without a time of day, so this audit excludes their full days from reference, retrofit and post-retrofit comparisons. This is a conservative analysis convention. The pre-retrofit period is the reference condition and may contain defects. [Provider chronology](https://bwk.kuleuven.be/bwm/kw51).

| Period | Dates inclusive, archive calendar | Scheduled hours | No mode | Bridge surface temp available | Vliet air temp available |
|---|---|---:|---:|---:|---:|
| Reference | 2018-10-01 to 2019-05-14 | 5,424 | 195 | 4,148 | 5,424 |
| Retrofit | 2019-05-16 to 2019-09-26 | 3,216 | 7 | 3,216 | 3,211 |
| Post-retrofit | 2019-09-28 to 2020-01-15 | 2,640 | 85 | 2,555 | 2,587 |
| Boundary days | 2019-05-15 and 2019-09-27 | 48 | 0 | 48 | 48 |

| Condition | Treatment |
|---|---|
| Unknown exact intervention boundary times | Exclude both boundary dates and report their 48 slots separately |
| Unidentified mode | Keep the hour and missing value. Require the selected mode panel for a valid score in the next milestone |
| No temperature for a conditioned model | Keep the hour as unavailable. Do not interpolate using observations after that hour |
| Non-positive frequency, infinite value or invalid archive time/layout | Reject the import explicitly |
| Temperature beyond fitting support | Flag separately in the next milestone and include in availability accounting |
| Missing or unavailable scheduled hour | Keep as a gap in operations and interrupt consecutive-hour persistence |

There are 61,042 missing entries out of 158,592 possible hourly frequency estimates (38.5%). Of the 5,424 reference hours, 1,276 lack bridge surface temperature. Vliet air temperature is available for every reference hour. Its reference range is −7.53 to 26.58 °C across the full reference period, compared with up to 41.31 °C during the retrofit. Fitting support must be measured again on the fitting partition. There is substantial paired coverage in several modes. For example, mode 3 has 5,179 reference hours with Vliet air temperature and 4,137 with bridge surface temperature. The audit does not select the modelling panel.

All six arch components first appear in the published mode shapes at 2019-09-27 13:00. The data paper documents the addition of the arch accelerometers in September 2019 and the resulting improvement in arch-mode identification. The paper also describes manually tuned mode tracking across the record. Consequently the experiment is a chronological replay of precomputed features. Its cross-period alarm and availability comparisons can reflect differences in sensor configuration, excitation and upstream tracking as well as structural behaviour. The retrofit window also includes changes during the works. Compare retrofit and post-retrofit separately, without inferring a damage onset time. [Data paper, Identified Modal Characteristics and Table 1](https://ascelibrary.com/doi/10.1061/%28ASCE%29BE.1943-5592.0001668).

## Reproducible check

Download the three named files from the manifest or their links on Zenodo and place them in the ignored data directory. The official file API URL in the manifest successfully returned the modal archive after an HTTP error on the record's download URL. Run from the repository root:

```powershell
.venv/Scripts/python.exe -X utf8 -m src.kw51 data/kw51/zenodo-3745914/trackedmodes.zip --output outputs/kw51_audit.json
```

The audit reports chronology, joint availability by temperature and mode, and the first/last finite mode-shape component per channel. It leaves absent values as NaNs in memory. The report uses scheduled hours as its denominator, including hours with no modal outputs. This differs from the source paper's identification-rate denominator of hours with collected data. Automated tests use small synthetic MATLAB archives, and the same command was exercised against the hash-verified release.

## Milestone 3 entry conditions

1. Use the frozen hour and phase definitions above. Predeclare the primary temperature candidate (Vliet air has the best reference availability). Evaluate it as a proxy with a sensitivity check for on-site surface temperature on paired hours.
2. Specify the chronological 60/20/20 reference allocation and a development-only mode eligibility rule before fitting. Use the fitting block for mode selection, model settings, residual covariance and environmental support. Document exclusions and gaps, and keep a fixed panel.
3. Compare the three agreed models on common eligible hours as well as reporting each one's operating coverage. Freeze thresholds from the distinct calibration block. Report reference alarm fractions, episodes per monitored time, and retrofit/post-retrofit response with an explicit extrapolation count.

Milestone 2 passes the data-availability gate for that limited comparison. No detector or threshold has been fitted.
