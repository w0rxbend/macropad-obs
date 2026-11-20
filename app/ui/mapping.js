// SPDX-License-Identifier: MIT
// The pad bar and the mapping editor (task 3.7). It draws the form `read_mapping` gives, edits it
// in place and sends it back with `write_mapping`. The rules (unknown members kept, stray targets
// dropped, the URL rule, the picker from OBS_LIST) live in host/app_core/src/forms.rs; this file
// only picks which picker an action shows. OBS names are set as text, never as markup.

import * as api from "./api.js";
import { $, announce, control, element, labelled, say, step } from "./dom.js";

// `list`: the picker an action's target comes from (docs/config.md, actions).
const ACTIONS = [
  { value: "none", text: "Nothing" },
  { value: "scene", text: "Switch scene", list: "scenes" },
  { value: "toggle_mute", text: "Toggle mute", list: "inputs" },
  { value: "toggle_record", text: "Toggle record" },
  { value: "toggle_stream", text: "Toggle stream" },
  { value: "transition", text: "Run transition" },
];
// A knob's push mutes the knob's own input, so it picks no input.
const PUSH_ACTIONS = ACTIONS.map((action) =>
  action.value === "toggle_mute" ? { value: action.value, text: "Toggle mute (this knob's input)" } : action,
);
const LIST_NAMES = { scenes: "Scene", inputs: "Input" };

const state = { mapping: null, lists: { scenes: [], inputs: [] } };

function targetOf(action) {
  return action.uuid === undefined ? null : { uuid: action.uuid, label: action.label };
}

function setTarget(action, reference) {
  delete action.uuid;
  delete action.label;
  if (reference) Object.assign(action, reference);
}

// A select over one OBS list. A stored reference OBS does not list (OBS away, scene gone) stays
// offered under its stored label, so reading and saving never loses it.
function referenceSelect(list, current, pick) {
  const choices = state.lists[list];
  const select = element("select", {}, element("option", { value: "", textContent: "(none)" }));
  if (current && !choices.some((choice) => choice.uuid === current.uuid)) {
    select.append(element("option", { value: current.uuid, textContent: `${current.label} (not in OBS list)` }));
  }
  const options = document.createDocumentFragment();
  for (const choice of choices) options.append(element("option", { value: choice.uuid, textContent: choice.label }));
  select.append(options);
  select.value = current ? current.uuid : "";
  select.addEventListener("change", () => {
    const known = choices.find((choice) => choice.uuid === select.value);
    pick(known ?? (current && current.uuid === select.value ? current : null));
  });
  return select;
}

// The action select and, when the action has one, its target picker. A new action starts with
// no target, so a scene never carries over as an input.
function actionParts(action, actions, title) {
  const body = element("div", { className: "parts" });
  const draw = () => {
    const select = element("select");
    for (const choice of actions) {
      select.append(element("option", { value: choice.value, textContent: choice.text, selected: choice.value === action.do }));
    }
    select.addEventListener("change", () => {
      action.do = select.value;
      setTarget(action, null);
      draw();
    });
    const parts = [labelled(title, select)];
    const list = actions.find((choice) => choice.value === action.do)?.list;
    if (list) {
      parts.push(labelled(LIST_NAMES[list], referenceSelect(list, targetOf(action), (picked) => setTarget(action, picked))));
    }
    body.replaceChildren(...parts);
  };
  draw();
  return body;
}

function knobControl(knob, index) {
  const stepInput = element("input", { type: "number", min: "0.1", max: "6", step: "0.1", value: String(knob.step_db) });
  stepInput.addEventListener("change", () => {
    knob.step_db = Number(stepInput.value);
  });
  const input = referenceSelect("inputs", knob.input, (picked) => {
    knob.input = picked;
  });
  return control(
    `Knob ${index + 1}`,
    labelled("Input", input),
    labelled("dB per detent", stepInput),
    actionParts(knob.push, PUSH_ACTIONS, "Push"),
  );
}

function drawMapping() {
  const mapping = state.mapping;
  $("#url").value = mapping.url;
  $("#keys").replaceChildren(...mapping.keys.map((key, index) => control(`Key ${index + 1}`, actionParts(key, ACTIONS, "Action"))));
  $("#buttons").replaceChildren(
    ...mapping.buttons.map((button, index) => control(`Button B${index + 1}`, actionParts(button, ACTIONS, "Action"))),
  );
  $("#knobs").replaceChildren(...mapping.knobs.map(knobControl));
  $("#editor").hidden = false;
}

async function checkUrl() {
  const url = $("#url").value;
  state.mapping.url = url;
  const note = $("#url-note");
  try {
    await api.checkUrl(url);
    note.textContent = "";
    $("#url").removeAttribute("aria-invalid");
  } catch (failure) {
    note.textContent = String(failure);
    $("#url").setAttribute("aria-invalid", "true");
  }
}

async function findPads() {
  const pads = await api.listPads();
  $("#pad").replaceChildren(
    ...pads.map((pad) => element("option", { value: pad.serial ?? "", textContent: `${pad.serial ?? "no serial"}  ${pad.path}` })),
  );
  say(pads.length === 0 ? "No pad found. Plug it in and press Find." : `Pads found: ${pads.length}.`);
}

async function readPad() {
  state.mapping = await api.readMapping();
  drawMapping();
  $("#stale").hidden = true;
  say("Read the pad's mapping.");
}

// One request at a time: the window's commands share one pad connection.
async function loadLists() {
  const scenes = await api.obsList("scenes");
  const inputs = await api.obsList("inputs");
  state.lists = { scenes, inputs };
  if (state.mapping) drawMapping();
  say(`OBS lists from the pad: ${scenes.length} scenes, ${inputs.length} inputs.`);
}

async function connectPad() {
  const info = await api.connect($("#pad").value || null);
  say(`Connected: firmware ${info.fw_version}, board rev ${info.board_rev}.`);
  announce("pad:connected");
  await readPad();
  await loadLists();
}

function closeEditor() {
  state.mapping = null;
  $("#editor").hidden = true;
}

async function disconnectPad() {
  await api.disconnect();
  announce("pad:disconnected");
  say("Disconnected.");
}

const shown = (value) => (value === null || value === undefined ? "(none)" : JSON.stringify(value));

async function save() {
  const saved = await api.writeMapping(state.mapping);
  if (saved.outcome === "saved") {
    $("#stale").hidden = true;
    say(`Saved. The pad's document is now seq ${saved.seq}.`);
    return;
  }
  $("#changes").replaceChildren(
    ...saved.changes.map((change) => element("li", { textContent: `${change.path}: pad ${shown(change.pad)}, yours ${shown(change.app)}` })),
  );
  $("#stale").hidden = false;
  say("Another write reached the pad first. Save again to keep yours, or Read to take the pad's.");
}

$("#find").addEventListener("click", () => step(findPads));
$("#connect").addEventListener("click", () => step(connectPad));
$("#disconnect").addEventListener("click", () => step(disconnectPad));
$("#read").addEventListener("click", () => step(readPad));
$("#lists").addEventListener("click", () => step(loadLists));
$("#url").addEventListener("input", () => step(checkUrl));
document.addEventListener("pad:disconnected", closeEditor);
$("#editor").addEventListener("submit", (event) => {
  event.preventDefault();
  step(save);
});
step(findPads);
