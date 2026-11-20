// SPDX-License-Identifier: MIT
// The display page (task 3.8): each panel's widgets with a live preview. The form is the
// `Layout` of host/app_core/src/forms.rs; the preview is the firmware's own fw-ui C, run by the
// core through the validator, so an invalid layout shows its path and the frames stay as they
// were. This file only draws inputs for each kind's fields; the rules stay in the core.

import * as api from "./api.js";
import { $, control, element, labelled, onPad, sayWritten, step } from "./dom.js";

const PANELS = [
  { name: "main_display", title: "Main display", width: 320, height: 480 },
  { name: "strip_display", title: "Strip display", width: 142, height: 428 },
];
// The fields of each widget kind and their choices (docs/config.md, "Widgets").
const KINDS = {
  status: { fields: { set: ["link", "rec", "live"] } },
  key: { key: { int: [0, 8] } },
  legend: { button: { int: [0, 3] } },
  scene_line: { scene: { one: ["program", "preview"] }, size: { one: ["small", "large"] } },
  strip: { knob: { int: [0, 2] }, parts: { set: ["name", "db", "fader", "meter", "push"] } },
  text: { text: { text: true } },
};
const GEOMETRY = ["x", "y", "w", "h"];
// The smallest side a widget takes (docs/config.md, rule 1): a new widget starts at this size.
const MIN_SIDE = 24;
const PREVIEW_DELAY_MS = 150;

const state = { layout: null, timer: 0 };

function startValue(spec) {
  if (spec.int) return spec.int[0];
  if (spec.one) return spec.one[0];
  if (spec.set) return [spec.set[0]];
  return "";
}

// A new kind starts with its own fields; the old kind's fields go.
function setKind(widget, kind) {
  for (const field of Object.keys(KINDS[widget.kind] ?? {})) delete widget[field];
  widget.kind = kind;
  for (const [field, spec] of Object.entries(KINDS[kind])) widget[field] = startValue(spec);
}

function changed() {
  clearTimeout(state.timer);
  state.timer = setTimeout(() => step(drawPreview), PREVIEW_DELAY_MS);
}

function numberInput(value, onValue, range = {}) {
  const input = element("input", { type: "number", step: "1", value: String(value), ...range });
  input.addEventListener("input", () => {
    onValue(Number(input.value));
    changed();
  });
  return input;
}

function choiceSelect(options, value, onValue) {
  const select = element("select");
  for (const option of options) select.append(element("option", { value: option, textContent: option, selected: option === value }));
  select.addEventListener("change", () => {
    onValue(select.value);
    changed();
  });
  return select;
}

// Checkboxes for a list of names, kept in the order the kind lists them.
function setChecks(options, widget, field) {
  const boxes = options.map((option) => element("input", { type: "checkbox", checked: widget[field].includes(option) }));
  for (const box of boxes) {
    box.addEventListener("change", () => {
      widget[field] = options.filter((_, index) => boxes[index].checked);
      changed();
    });
  }
  return element("div", { className: "row" }, ...boxes.map((box, index) => element("label", { className: "check" }, box, options[index])));
}

function fieldInput(widget, field, spec) {
  const assign = (value) => {
    widget[field] = value;
  };
  if (spec.set) return setChecks(spec.set, widget, field);
  if (spec.one) return labelled(field, choiceSelect(spec.one, widget[field], assign));
  if (spec.int) return labelled(field, numberInput(widget[field], assign, { min: String(spec.int[0]), max: String(spec.int[1]) }));
  const input = element("input", { value: widget[field] ?? "", autocomplete: "off" });
  input.addEventListener("input", () => {
    assign(input.value);
    changed();
  });
  return labelled(field, input);
}

function widgetControl(widgets, index) {
  const widget = widgets[index];
  const kind = choiceSelect(Object.keys(KINDS), widget.kind, (picked) => {
    setKind(widget, picked);
    drawWidgets();
  });
  const geometry = GEOMETRY.map((side) =>
    labelled(side, numberInput(widget[side], (value) => {
      widget[side] = value;
    }, { min: "0" })),
  );
  const fields = Object.entries(KINDS[widget.kind] ?? {}).map(([field, spec]) => fieldInput(widget, field, spec));
  const remove = element("button", { type: "button", textContent: "Remove" });
  remove.addEventListener("click", () => {
    widgets.splice(index, 1);
    drawWidgets();
    changed();
  });
  return control(`Widget ${index + 1}`, labelled("Kind", kind), element("div", { className: "grid sides" }, ...geometry), ...fields, remove);
}

function drawWidgets() {
  for (const panel of PANELS) {
    const widgets = state.layout[panel.name];
    $(`#widgets-${panel.name}`).replaceChildren(...widgets.map((_, index) => widgetControl(widgets, index)));
  }
}

function addWidget(panel) {
  const widget = { kind: "text", x: 0, y: 0, w: MIN_SIDE, h: MIN_SIDE };
  setKind(widget, "text");
  state.layout[panel.name].push(widget);
  drawWidgets();
  changed();
}

// One panel's frame from big-endian RGB565 to the canvas.
function paint(panel, rgb565) {
  const context = $(`#preview-${panel.name}`).getContext("2d");
  const image = context.createImageData(panel.width, panel.height);
  for (let pixel = 0; pixel < panel.width * panel.height; pixel++) {
    const value = (rgb565[2 * pixel] << 8) | rgb565[2 * pixel + 1];
    const red = value >> 11;
    const green = (value >> 5) & 0x3f;
    const blue = value & 0x1f;
    image.data.set([(red << 3) | (red >> 2), (green << 2) | (green >> 4), (blue << 3) | (blue >> 2), 255], 4 * pixel);
  }
  context.putImageData(image, 0, 0);
}

async function drawPreview() {
  const note = $("#layout-note");
  try {
    const frames = new Uint8Array(await api.preview(state.layout));
    let offset = 0;
    for (const panel of PANELS) {
      const bytes = panel.width * panel.height * 2;
      paint(panel, frames.subarray(offset, offset + bytes));
      offset += bytes;
    }
    note.textContent = "";
  } catch (failure) {
    note.textContent = `Preview: ${failure}`;
  }
}

function buildPanels() {
  $("#panels").replaceChildren(
    ...PANELS.map((panel) => {
      const add = element("button", { type: "button", textContent: "Add widget" });
      add.addEventListener("click", () => addWidget(panel));
      const canvas = element("canvas", { id: `preview-${panel.name}`, width: panel.width, height: panel.height });
      canvas.setAttribute("aria-label", `${panel.title} preview`);
      return element(
        "div",
        { className: "panel" },
        element("figure", {}, canvas, element("figcaption", { textContent: `${panel.title}, ${panel.width} x ${panel.height}` })),
        element("div", { className: "parts" }, element("div", { id: `widgets-${panel.name}`, className: "parts" }), add),
      );
    }),
  );
}

async function readLayout() {
  state.layout = await api.readLayout();
  drawWidgets();
  $("#display-page").hidden = false;
  await drawPreview();
}

async function save() {
  sayWritten(await api.writeLayout(state.layout));
}

buildPanels();
onPad("pad:connected", readLayout);
document.addEventListener("pad:disconnected", () => {
  state.layout = null;
  $("#display-page").hidden = true;
});
$("#layout-read").addEventListener("click", () => step(readLayout));
$("#layout-save").addEventListener("click", () => step(save));
