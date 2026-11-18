"""Fetch prespecified KW51 ambient recordings by ZIP byte range using curl."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from zlib import crc32


SOURCE = "https://zenodo.org/api/records/3745914/files"
NAME = re.compile(r"ambient_(\d{8})_(\d{6})\.mat$")
TAIL_BYTES = 65557
MAX_MEMBER_BYTES = 30_000_000


def scheduled_hours():
    """A bounded pilot across one reference month and two intervention periods."""
    for day in range(1, 31):
        period = "fit" if day <= 10 else "calibration" if day <= 20 else "reference_test"
        for hour in ((0, 12) if day <= 20 else (0,)):
            yield period, datetime(2019, 4, day, hour)
    for period, year, month in (("retrofit", 2019, 7), ("post_retrofit", 2020, 1)):
        for day in (1, 3, 5, 7, 9, 11):
            yield period, datetime(year, month, day)


class RangeZip:
    """A seekable HTTP stream with one cached range. Refuses full-file responses."""

    def __init__(self, archive):
        self.url = f"{SOURCE}/{archive}/content"
        self.position = 0
        self.size = None
        self.offset, self.cache = self._fetch(f"-{TAIL_BYTES}", TAIL_BYTES)

    def _fetch(self, interval, limit):
        with TemporaryDirectory() as directory:
            headers = Path(directory) / "headers"
            run = subprocess.run(
                ["curl", "-fsSL", "--retry", "1", "--connect-timeout", "10",
                 "--max-time", "90", "--max-filesize", str(limit), "--range", interval,
                 "--dump-header", str(headers), self.url],
                capture_output=True, timeout=195,
            )
            if run.returncode:
                raise OSError(f"Range {interval} failed: {run.stderr.decode(errors='replace').strip()}")
            ranges = re.findall(r"^content-range:\s*bytes (\d+)-(\d+)/(\d+)",
                                headers.read_text(encoding="ascii", errors="replace"), re.I | re.M)
        if not ranges:
            raise OSError("Archive host did not return Content-Range")
        first, last, size = map(int, ranges[-1])
        expected = (max(0, size - int(interval[1:])), size - 1) if interval.startswith("-") else (
            int(interval.split("-")[0]), min(int(interval.split("-")[1]), size - 1)
        )
        if (
            (first, last) != expected or len(run.stdout) != last - first + 1
            or len(run.stdout) > limit or (self.size is not None and self.size != size)
        ):
            raise OSError("Archive range response did not match the request")
        self.size = size
        return first, run.stdout

    def clone(self):
        copy = object.__new__(RangeZip)
        copy.url, copy.size = self.url, self.size
        copy.offset, copy.cache, copy.position = self.offset, self.cache, 0
        return copy

    def seek(self, offset, whence=0):
        self.position = (0, self.position, self.size)[whence] + offset
        if self.position < 0:
            raise OSError("Cannot seek before the archive start")
        return self.position

    def tell(self):
        return self.position

    def seekable(self):
        return True

    def read(self, length=-1):
        end = self.size if length < 0 else min(self.size, self.position + length)
        if end <= self.position:
            return b""
        if not self.offset <= self.position <= end <= self.offset + len(self.cache):
            if end - self.position > MAX_MEMBER_BYTES:
                raise OSError("Range request exceeds the pilot's per-member limit")
            self.offset, self.cache = self._fetch(f"{self.position}-{end - 1}", end - self.position)
        result = self.cache[self.position - self.offset:end - self.offset]
        self.position = end
        return result

    def member(self, info, archive):
        if max(info.file_size, info.compress_size) > MAX_MEMBER_BYTES - TAIL_BYTES:
            raise OSError("ZIP member exceeds the pilot byte limit")
        start = info.header_offset
        end = min(self.size, start + info.compress_size + TAIL_BYTES)
        self.offset, self.cache = self._fetch(f"{start}-{end - 1}", end - start)
        # ZipFile validates compression and CRC. Re-use its parsed central directory.
        with archive.open(info) as member:
            return member.read(MAX_MEMBER_BYTES)


def _select(archive, hour):
    candidates = []
    for info in archive.infolist():
        match = NAME.fullmatch(Path(info.filename).name)
        if match:
            stamp = datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
            if hour <= stamp < hour + timedelta(hours=1):
                candidates.append((stamp, info.filename))
    return min(candidates)[1] if candidates else None


def fetch(destination, workers=4, limit=None):
    destination.mkdir(parents=True, exist_ok=True)
    archives = {}
    jobs = []
    for period, hour in scheduled_hours():
        if limit is not None and len(jobs) >= limit:
            break
        name = f"ambient_{hour:%Y%m}.zip"
        if name not in archives:
            indexed = RangeZip(name)
            archives[name] = indexed, ZipFile(indexed)
        indexed, directory = archives[name]
        jobs.append((period, hour, name, _select(directory, hour)))

    def download(job):
        period, hour, source, name = job
        row = {"period": period, "scheduled_hour_utc": hour.isoformat() + "Z", "archive": source}
        if name is None:
            return {**row, "status": "not_in_archive"}
        indexed, directory = archives[source]
        stream = indexed.clone()
        info = directory.getinfo(name)
        path = destination / Path(name).name
        try:
            if path.exists():
                raw = path.read_bytes()
                if len(raw) != info.file_size or crc32(raw) != info.CRC:
                    raise OSError(f"Existing member CRC/size differs: {path.name}")
            else:
                with ZipFile(stream) as archive:
                    raw = stream.member(info, archive)
                with path.open("xb") as output:
                    output.write(raw)
            return {
                **row, "status": "downloaded", "member": name, "file": path.name,
                "size": len(raw), "zip_crc32": f"{info.CRC:08x}", "sha256": hashlib.sha256(raw).hexdigest(),
            }
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            return {**row, "member": name, "status": "retrieval_failed", "reason": str(exc)}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = []
        for row in pool.map(download, jobs):
            rows.append(row)
            print(row["scheduled_hour_utc"], row["status"], flush=True)
    path = destination / "manifest.json"
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 7))
    parser.add_argument("--limit", type=int, help="Optional initial record limit for a download smoke check")
    args = parser.parse_args()
    fetch(args.destination, args.workers, args.limit)
