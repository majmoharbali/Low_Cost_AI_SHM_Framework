"use strict";

const replay = JSON.parse(document.getElementById("replay-data").textContent);
const byId = (id) => document.getElementById(id);
const period = byId("period");
const condition = byId("condition");
const hour = byId("hour");
const pair = new Set(replay.scenarios.engineered2.channels);
const periods = {reference_test: "Reference test", retrofit: "During retrofit", post_retrofit: "After retrofit"};
const conditions = {
  clean: "Measured, provider-preprocessed acceleration.",
  noise_5db: "Added noise at a nominal 5 dB signal-to-noise ratio.",
  dc_bias: "Applied a constant offset of ±0.002 m/s² by channel.",
  timing: "Applied up to 58.1 ms of relative skew across each layout.",
  burst: "Inserted a two-second gap into one channel at selected scheduled hours.",
};
const reasons = {
  incomplete_full_deck: "Incomplete six-channel crop",
  too_short_for_common_crop: "Capture too short for the common crop",
};

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function explain(reason) {
  return reasons[reason] ?? reason?.replaceAll("_", " ") ?? "Estimate unavailable";
}

function timeLabel(value) {
  return value.slice(0, 16).replace("T", " ");
}

function selectStation(station, button) {
  byId("deck-plan").querySelectorAll("button").forEach((item) => {
    item.setAttribute("aria-pressed", String(item === button));
  });
  const side = station.girder === "A" ? "south" : "north";
  const list = node("ul");
  for (const channel of station.channels) {
    const row = node("li");
    row.append(node("code", channel));
    row.append(node("span", channel.endsWith("y") ? "Lateral (y)" : "Vertical (z)"));
    row.append(pair.has(channel)
      ? node("span", "Retained in pair", "pair-text")
      : node("span", "Full deck only"));
    list.append(row);
  }
  byId("station-detail").replaceChildren(
    node("h3", `Girder ${station.girder} (${side}) · Model x = ${station.x_m.toFixed(3)} m`),
    list,
  );
}

for (const station of replay.stations) {
  const hasPair = station.channels.some((channel) => pair.has(channel));
  const button = node("button", station.name, hasPair ? "station has-pair" : "station");
  button.classList.toggle("north", station.girder === "C");
  button.type = "button";
  button.style.left = `${station.left_pct}%`;
  button.style.top = `${station.top_pct}%`;
  button.setAttribute("aria-pressed", "false");
  button.setAttribute("aria-label", `Station ${station.name}, ${station.channels.join(", ")}${hasPair ? ", includes a retained channel" : ""}`);
  button.addEventListener("click", () => selectStation(station, button));
  byId("deck-plan").append(button);
  if (station.channels.includes("aBD17Ay")) selectStation(station, button);
}

function flagCell(result) {
  if (result.flag === null) return node("td", "Unavailable", "unavailable");
  return result.flag ? node("td", "Change flag", "flag") : node("td", "No flag");
}

function modeCell(result, index) {
  const mode = result.modes?.[index];
  if (mode?.frequency_hz != null) return node("td", `${mode.frequency_hz.toFixed(3)} Hz`);
  const cell = node("td", "—", "unavailable");
  cell.append(node("small", explain(mode?.reason ?? result.record_reason)));
  return cell;
}

function tableRow(label, first, second) {
  const row = node("tr");
  const heading = node("th", label);
  heading.scope = "row";
  row.append(heading, first, second);
  return row;
}

function selectedRows() {
  const suffix = condition.value === "clean" ? "" : `_${condition.value}`;
  const full = replay.scenarios[`full6${suffix}`].acquisitions;
  const reduced = new Map(replay.scenarios[`engineered2${suffix}`].acquisitions.map((record) => [record.hour_utc, record]));
  return full.filter((record) => record.period in periods && (
    period.value === "heldout" || record.period === period.value
  )).map((record) => [record, reduced.get(record.hour_utc)]);
}

function inspectHour(rows) {
  const [full, reduced] = rows.find(([record]) => record.hour_utc === hour.value);
  byId("record-period").textContent = periods[full.period];
  byId("results").replaceChildren(
    tableRow("Change decision", flagCell(full), flagCell(reduced)),
    ...replay.mode_ids.map((id, index) => tableRow(
      `Mode ${id}${replay.scoring_panel.includes(id) ? " *" : ""}`,
      modeCell(full, index), modeCell(reduced, index),
    )),
  );
  byId("record-note").textContent = `* Modes used in the change score. Spectral bin: ${replay.bin_hz.toFixed(4)} Hz.`;
  for (const row of byId("hours").rows) row.setAttribute("aria-current", String(row.dataset.hour === hour.value));
}

function refresh() {
  const rows = selectedRows();
  const previous = hour.value;
  const shared = rows.filter(([a, b]) => a.flag !== null && b.flag !== null);
  const availableModes = rows.flatMap(([a, b]) => (a.modes ?? []).flatMap((mode, i) => (
    mode.frequency_hz === null ? [] : [b.modes?.[i]?.frequency_hz != null]
  )));
  byId("coverage").textContent = `${shared.length} / ${rows.length}`;
  byId("agreement").textContent = shared.length ? `${shared.filter(([a, b]) => a.flag === b.flag).length} / ${shared.length}` : "—";
  byId("retained").textContent = availableModes.length ? `${availableModes.filter(Boolean).length} / ${availableModes.length}` : "—";
  byId("condition-note").textContent = conditions[condition.value];
  hour.replaceChildren(...rows.map(([record]) => {
    const option = node("option", timeLabel(record.hour_utc));
    option.value = record.hour_utc;
    return option;
  }));
  const preferred = shared.find(([record]) => record.period === "post_retrofit") ?? shared[0] ?? rows[0];
  hour.value = rows.some(([record]) => record.hour_utc === previous) ? previous : preferred[0].hour_utc;
  byId("hours").replaceChildren(...rows.map(([a, b]) => {
    const row = node("tr");
    row.dataset.hour = a.hour_utc;
    const cell = node("th");
    cell.scope = "row";
    const button = node("button", timeLabel(a.hour_utc));
    button.type = "button";
    button.addEventListener("click", () => {
      hour.value = a.hour_utc;
      inspectHour(rows);
      hour.focus();
    });
    cell.append(button);
    row.append(cell, node("td", periods[a.period]), flagCell(a), flagCell(b));
    return row;
  }));
  inspectHour(rows);
}

period.addEventListener("change", refresh);
condition.addEventListener("change", refresh);
hour.addEventListener("change", () => inspectHour(selectedRows()));
byId("source-link").addEventListener("click", () => { byId("sources").open = true; });
for (const [label, hash] of Object.entries({
  "Replay report SHA-256": replay.report_sha256,
  "Recording manifest SHA-256": replay.manifest_sha256,
  ...replay.drawing_hashes,
})) {
  byId("provenance").append(node("dt", label), node("dd", hash));
}
refresh();
