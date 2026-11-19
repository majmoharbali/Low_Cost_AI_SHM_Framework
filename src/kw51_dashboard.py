"""Package a local KW51 replay report and drawing crops into an offline dashboard."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory


# Coordinates from the supplied select_sensors.m and model_kw51.m.
STATIONS = [
    {"name": "A · 11", "girder": "A", "x_m": 34.558, "channels": ["aBD11Az"]},
    {"name": "A · 17", "girder": "A", "x_m": 58.158, "channels": ["aBD17Ay", "aBD17Az"]},
    {"name": "C · 17", "girder": "C", "x_m": 58.158, "channels": ["aBD17Cz"]},
    {"name": "A · 23", "girder": "A", "x_m": 81.758, "channels": ["aBD23Ay", "aBD23Az"]},
]
OVERVIEW = Path("Other/overview.pdf")
GENERAL_PLAN = Path("(KW51 - 01A) - GTN-D0-L201-03-003A.pdf")


def _crop(source, dpi, rectangle, stem):
    left, top, width, height = rectangle
    try:
        subprocess.run(
            ["pdftoppm", "-f", "1", "-l", "1", "-singlefile", "-r", str(dpi),
             "-x", str(left), "-y", str(top), "-W", str(width), "-H", str(height),
             "-png", str(source), str(stem)],
            check=True, capture_output=True,
        )
    except FileNotFoundError:
        raise ValueError("Put Poppler's pdftoppm executable on PATH to render the supplied PDFs") from None
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Could not render {source.name}: {exc.stderr.decode(errors='replace')}") from exc
    encoded = base64.b64encode(stem.with_suffix(".png").read_bytes()).decode("ascii")
    return "data:image/png;base64," + encoded


def package(report_path, blueprints, output):
    raw = report_path.read_bytes()
    report = json.loads(raw)
    scenarios = {
        key: value for key, value in report["scenarios"].items()
        if value["frozen_model"] in ("full6", "engineered2")
    }
    if not {"full6", "engineered2"} <= scenarios.keys() or not all(
        value.get("acquisitions") for value in scenarios.values()
    ):
        raise ValueError("Generate a pilot report with --acquisitions first")
    known_channels = {channel for station in STATIONS for channel in station["channels"]}
    if set(scenarios["full6"]["channels"]) != known_channels or any(
        not set(value["channels"]) <= known_channels for value in scenarios.values()
    ):
        raise ValueError("Replay channels do not match the supplied KW51 map")

    # Register the overview plan against its bearing centres, using the
    # model's Brussels-to-Leuven bearing x coordinates (1.059 and 115.257 m).
    # Image points are page pixels at 210 dpi before cropping.
    crop = (16, 452, 1138, 241)
    left, top, width, height = crop
    stations = []
    for station in STATIONS:
        fraction = (station["x_m"] - 1.059) / (115.257 - 1.059)
        page_x = 90 + (1091 - 90) * fraction
        page_y = {"A": 623, "C": 518}[station["girder"]]
        stations.append({**station, "left_pct": (page_x - left) / width * 100,
                         "top_pct": (page_y - top) / height * 100})

    sources = (blueprints / OVERVIEW, blueprints / GENERAL_PLAN)
    with TemporaryDirectory(dir=output.parent) as temporary:
        preview = Path(temporary)
        plan = _crop(sources[0], 210, crop, preview / "plan")
        general_plan = _crop(sources[1], 100, (234, 154, 3600, 760), preview / "general")

    payload = {
        "report_sha256": hashlib.sha256(raw).hexdigest(),
        "manifest_sha256": report["manifest_sha256"],
        "drawing_hashes": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        "bin_hz": report["bin_hz"], "scoring_panel": report["scoring_panel"],
        "mode_ids": [int(key) for key in report["development_modes"]],
        "scenarios": scenarios, "stations": stations,
    }
    templates = Path(__file__).resolve().parents[1] / "dashboard" / "kw51"
    html = (templates / "index.html").read_text(encoding="utf-8")
    substitutions = {
        "/* REPLAY_CSS */": (templates / "replay.css").read_text(encoding="utf-8"),
        "/* REPLAY_JS */": (templates / "replay.js").read_text(encoding="utf-8"),
        "__REPLAY_DATA__": json.dumps(payload, allow_nan=False).replace("<", "\\u003c"),
        "__PLAN__": plan, "__GENERAL_PLAN__": general_plan,
    }
    for marker, content in substitutions.items():
        html = html.replace(marker, content)
    with output.open("x", encoding="utf-8", newline="\n") as file:
        file.write(html)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("blueprints", type=Path, help="Supplied KW51 blueprints directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        package(args.report, args.blueprints, args.output)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        parser.exit(2, f"Dashboard export failed: {exc}\n")
    print(args.output)


if __name__ == "__main__":
    main()
