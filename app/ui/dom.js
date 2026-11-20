// SPDX-License-Identifier: MIT
// What every page of the window shares: the status line, one user step at a time, element
// building (text is set as text, never as markup), and the pad events. `pad:connected` fires
// after a connect, `pad:disconnected` after a disconnect or an update, which ends the session.

export const $ = (selector) => document.querySelector(selector);

export function say(text) {
  $("#status").textContent = text;
}

// Runs one user step; a rejected command shows its Failure line.
export async function step(task) {
  try {
    await task();
  } catch (failure) {
    say(String(failure));
  }
}

export function element(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  node.append(...children);
  return node;
}

export function labelled(text, control) {
  return element("label", {}, element("span", { textContent: text }), control);
}

export function control(title, ...parts) {
  return element("fieldset", { className: "control" }, element("legend", { textContent: title }), ...parts);
}

export function announce(name) {
  document.dispatchEvent(new Event(name));
}

export function onPad(name, handler) {
  document.addEventListener(name, () => step(handler));
}

// The status line after a page's write: `Saved` from the core.
export function sayWritten(saved) {
  if (saved.outcome === "saved") {
    say(`Saved. The pad's document is now seq ${saved.seq}.`);
  } else {
    say(`Another write reached the pad first (${saved.changes.length} changes). Save again to keep yours, or Read to take the pad's.`);
  }
}
