// Run with npm-installed jsdom; browser layout itself is not emulated here.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
// Normal npm installs (including CI) take precedence over archived local deps.
const dependencyRequire = fs.existsSync(path.join(__dirname, "../node_modules/jsdom/package.json"))
  ? require : createRequire(path.join(__dirname, "../.work/package.json"));
const { JSDOM } = dependencyRequire("jsdom");
const script = fs.readFileSync(path.join(__dirname, "../custom_components/enigmaha_companion/panel.js"), "utf8");
const tick = () => new Promise(resolve => setImmediate(resolve));

async function createPanel({lazySelectors = false, lazySortable = false, brokenSelectors = false,
  savedLanguage, blockedStorage = false, hassBeforeConnect = false} = {}) {
  const dom = new JSDOM("<!doctype html><body></body>", {url: "http://ha.test", runScripts: "outside-only"});
  if (savedLanguage !== undefined) dom.window.localStorage.setItem("enigmaha_companion.language", savedLanguage);
  if (blockedStorage) Object.defineProperty(dom.window, "localStorage", {
    get() { throw new dom.window.DOMException("Storage disabled", "SecurityError"); },
  });
  for (const method of ["alert", "confirm", "prompt"]) {
    dom.window[method] = () => { throw new Error("Browser dialogs must not be used"); };
  }
  // jsdom does not implement the browser's modal top layer/focus trap.
  dom.window.HTMLDialogElement.prototype.showModal = function() { this.open = true; };
  dom.window.HTMLDialogElement.prototype.close = function() {
    this.open = false;
    this.dispatchEvent(new dom.window.Event("close"));
  };
  for (const tag of ["ha-button", "ha-icon-button"]) {
    dom.window.customElements.define(tag, class extends dom.window.HTMLElement {
      connectedCallback() { this.tabIndex = 0; }
    });
  }
  const scrolled = [];
  dom.window.HTMLElement.prototype.scrollIntoView = function(options) { scrolled.push({row: this, options}); };
  dom.window.requestAnimationFrame = callback => queueMicrotask(() => callback(0));
  const layoutMedia = new dom.window.EventTarget();
  layoutMedia.matches = false;
  dom.window.matchMedia = query => query === "(max-width:900px)" ? layoutMedia : {matches: false};
  // Exercise our native selector configuration and events; HA's own picker UI
  // is provided by HA, not reimplemented by this integration or these tests.
  let loads = 0;
  const defineSelector = () => dom.window.customElements.define("ha-selector", class extends dom.window.HTMLElement {});
  const defineInput = () => dom.window.customElements.define("ha-input", class extends dom.window.HTMLElement {});
  const defineSortable = () => dom.window.customElements.define("ha-sortable", class extends dom.window.HTMLElement {});
  if (!lazySelectors && !brokenSelectors) { defineSelector(); defineInput(); }
  if (!lazySelectors && !lazySortable && !brokenSelectors) defineSortable();
  dom.window.loadCardHelpers = async () => {
    loads++;
    if (brokenSelectors) throw new Error("test bundle unavailable");
    return {createCardElement: () => ({constructor: {getConfigElement: async () => {
      if (!dom.window.customElements.get("ha-selector")) defineSelector();
      if (!dom.window.customElements.get("ha-input")) defineInput();
      if (!dom.window.customElements.get("ha-sortable")) defineSortable();
    }}})};
  };
  dom.window.eval(script);
  const panel = dom.window.document.createElement("enigmaha-panel");
  if (!hassBeforeConnect) dom.window.document.body.append(panel);
  let saved;
  let failSave = false;
  const model = {schema_version: 1, revision: 1, display: {font_family: "Regular", font_size: 28},
    root: {type: "menu", id: "home", label: "Home Assistant", children: []}};
  const requests = [];
  const compatibilityRequests = [];
  panel.hass = {
    states: {
      "light.ceiling": {entity_id: "light.ceiling", attributes: {friendly_name: "Lampe <img src=x>"}, state: "off"},
      "sensor.temp": {entity_id: "sensor.temp", attributes: {friendly_name: "Temperatur", device_class: "temperature"}, state: "22"},
      "sensor.power": {entity_id: "sensor.power", attributes: {friendly_name: "Leistung", device_class: "power"}, state: "15"},
    },
    entities: {"light.ceiling": {device_id: "lamp"}, "sensor.temp": {area_id: "living", device_id: "meter"},
      "sensor.power": {device_id: "meter"}},
    devices: {lamp: {area_id: "living"}, meter: {area_id: "hall"}},
    callApi: async (method, route, body) => {
    if (route.endsWith("/compatibility")) {
      compatibilityRequests.push(route);
      return {version: "1.0.0", receivers: []};
    }
    requests.push(route);
    if (method === "PUT") {
      if (failSave) throw {status_code: 409};
      saved = JSON.parse(JSON.stringify(body));
      return {...saved, revision: body.revision + 1};
    }
    return JSON.parse(JSON.stringify(model));
  }};
  if (hassBeforeConnect) dom.window.document.body.append(panel);
  await tick();
  const root = panel.shadowRoot;
  const button = text => [...root.querySelectorAll("ha-button, ha-icon-button")].find(node => (node.label || node.textContent) === text);
  const select = (name, value) => {
    const control = root.querySelector(`[data-selector="${name}"], [data-field="${name}"]`);
    if (control.localName === "ha-input") {
      control.value = String(value ?? "");
      control.dispatchEvent(new dom.window.Event("input", {bubbles: true, composed: true}));
    } else control.dispatchEvent(
      new dom.window.CustomEvent("value-changed", {detail: {value}, bubbles: true, composed: true}));
  };
  return {dom, panel, root, button, select, requests, compatibilityRequests, scrolled, layoutMedia, loads: () => loads, saved: () => saved, fail: () => {failSave = true;}};
}

test("version status refresh warns about all receivers without changing unsaved fields", async () => {
  const ui = await createPanel();
  try {
    assert.equal(ui.compatibilityRequests.length, 1);
    assert.match(ui.root.querySelector(".compatibility").textContent, /Noch keine Receiver-Anfrage/);
    ui.select("new-menu", "Wohnzimmer");
    ui.button("Untermenü hinzufügen").click();
    const field = ui.root.querySelector('[data-field="menu-label"]');
    const model = JSON.stringify(ui.panel.model);
    ui.panel._hass.callApi = async () => ({version: "1.0.0", protocol_version: 1, receivers: [
      {address: "192.0.2.1", version: "0.9.0", protocol_version: 1, status: "version_mismatch"},
      {address: "192.0.2.2", version: "1.0.0", status: "compatible"},
      {address: "192.0.2.3", version: "1.0.0", protocol_version: 2, status: "protocol_mismatch"},
      {address: "<img src=x>", version: null, status: "unidentified_peer"},
    ]});
    await ui.panel.loadCompatibility();
    const status = ui.root.querySelector(".compatibility");
    assert.match(status.textContent, /Release 0\.9\.0 unterscheidet sich von HA 1\.0\.0/);
    assert.match(status.textContent, /Protokoll 1 passt; Verbindung freigegeben/);
    assert.match(status.textContent, /Protokoll 2 passt nicht zu HA 1/);
    assert.equal(status.querySelector('a[href="/config/repairs"]').textContent, "Reparaturen öffnen");
    assert.deepEqual([...status.querySelectorAll(".release-link")].map(a => a.href), [
      "https://github.com/topic2k/EnigmaHAcompanion/releases/tag/v1.0.0",
      "https://github.com/topic2k/EnigmaHAcompanion/releases/tag/v0.9.0"]);
    assert.match(status.textContent, /192\.0\.2\.2: Version 1\.0\.0 passt/);
    assert.equal(status.querySelectorAll(".version-warning").length, 2);
    assert.equal(status.querySelector("img"), null);
    assert.equal(JSON.stringify(ui.panel.model), model);
    assert.equal(ui.panel.dirty, true);
    assert.equal(ui.root.querySelector('[data-field="menu-label"]'), field);
    ui.panel.setLanguage("en");
    assert.match(ui.root.querySelector(".compatibility").textContent, /connection allowed/);
    assert.match(ui.root.querySelector(".compatibility").textContent, /Protocol 2 does not match HA 1/);
    ui.panel._hass.callApi = async () => ({version: "1.0.0", receivers: [
      {address: "192.0.2.1", version: "1.0.0", status: "compatible"},
    ]});
    await ui.panel.loadCompatibility();
    assert.equal(ui.root.querySelectorAll(".version-warning").length, 0);
    ui.panel._hass.callApi = async () => { throw new Error("offline"); };
    await ui.panel.loadCompatibility();
    assert.match(ui.root.querySelector(".compatibility").textContent, /Version check unavailable/);
    ui.panel.remove();
    let requests = 0;
    ui.panel._hass.callApi = async () => { requests++; };
    await ui.panel.loadCompatibility();
    assert.equal(requests, 0);
  } finally { ui.dom.window.close(); }
});

test("initial HA assignment before connection loads the editor without another state update", async () => {
  const ui = await createPanel({hassBeforeConnect: true});
  try {
    assert.equal(ui.requests.length, 1);
    assert.equal(ui.panel.model.root.label, "Home Assistant");
    assert.ok(ui.root.querySelector("[data-selector='language']"));
  } finally { ui.dom.window.close(); }
});

test("coordinated update requires confirmation and pins the release and participating receivers", async () => {
  const ui = await createPanel();
  try {
    const candidate = {id: "release-candidate", release: {version: "2.0.0"}};
    ui.panel.compatibility = {version: "1.0.0", receivers: [{id: "a".repeat(32), address: "192.0.2.1", version: "1.0.0", status: "compatible"}],
      updates: {hacs: {entity_id: "update.renamed"}, candidate, job: null}};
    const calls = [];
    ui.panel._hass.callApi = async (method, route, body) => {
      calls.push({method, route, body});
      return {hacs: {}, candidate, job: {id: "job", release: {version: "2.0.0"}, phase: "ha_installing", receivers: []}};
    };
    ui.select("new-menu", "Ungespeichert");
    ui.button("Untermenü hinzufügen").click();
    const draft = JSON.stringify(ui.panel.model);
    ui.panel.renderCompatibility();
    ui.button("Beide auf 2.0.0 aktualisieren").click();
    assert.match(ui.root.querySelector("dialog").textContent, /192\.0\.2\.1/);
    assert.equal(calls.length, 0);
    ui.button("Abbrechen").click();
    await tick();
    assert.equal(calls.length, 0);
    ui.button("Beide auf 2.0.0 aktualisieren").click();
    // A live status refresh cannot add unconfirmed receivers to the request.
    ui.panel.compatibility.receivers.push({id: "c".repeat(32), address: "192.0.2.2"});
    ui.button("Update starten").click();
    await tick();
    assert.equal(calls.length, 1);
    assert.deepEqual(JSON.parse(JSON.stringify(calls[0])), {method: "POST", route: "enigmaha_companion/v1/updates",
      body: {action: "start", candidate_id: "release-candidate", receiver_ids: ["a".repeat(32)]}});
    assert.equal(JSON.stringify(ui.panel.model), draft);
    assert.equal(ui.panel.dirty, true);
  } finally { ui.dom.window.close(); }
});

test("HA restart requires separate consent and saved edits; HACS absence and failure are visible", async () => {
  const ui = await createPanel();
  try {
    const job = {id: "job", release: {version: "2.0.0"}, phase: "ha_restart_required", receivers: [
      {address: "192.0.2.1", status: "completed"}]};
    ui.panel.compatibility.updates = {hacs: {}, candidate: null, job};
    ui.panel.renderCompatibility();
    ui.panel.markDirty();
    ui.panel.renderCompatibility();
    assert.equal(ui.button("Home Assistant neu starten").disabled, true);
    const calls = [];
    ui.panel._hass.callApi = async (method, route, body) => { calls.push(body); return ui.panel.compatibility.updates; };
    ui.panel.dirty = false;
    ui.panel.renderCompatibility();
    ui.button("Home Assistant neu starten").click();
    assert.equal(calls.length, 0);
    ui.button("Abbrechen").click();
    await tick();
    assert.equal(calls.length, 0);
    ui.button("Home Assistant neu starten").click();
    ui.button("Neu starten").click();
    await tick();
    assert.deepEqual(JSON.parse(JSON.stringify(calls)), [{action: "restart", job_id: "job"}]);
    assert.match(ui.root.querySelector(".compatibility").textContent, /HA-Neustart angefordert/);
    ui.panel.compatibility.updates = {hacs: null, candidate: null, job: null};
    ui.panel.renderCompatibility();
    assert.match(ui.root.querySelector(".compatibility").textContent, /HACS-Update nicht verfügbar/);
    ui.panel.compatibility.updates.job = job;
    ui.panel.renderCompatibility();
    assert.match(ui.root.querySelector(".compatibility").textContent, /Receiver verwenden die Zielversion/);
    ui.panel.compatibility.updates.job = null;
    ui.panel.compatibility.updates.hacs = {};
    ui.panel._hass.callApi = async () => { throw {body: {error: "release_check_failed"}}; };
    await ui.panel.updateAction({action: "check"});
    assert.match(ui.root.querySelector(".compatibility").textContent, /Release nicht verfügbar oder unvollständig/);
    ui.panel.setLanguage("en");
    assert.match(ui.root.querySelector(".compatibility").textContent, /Release unavailable or incomplete/);
  } finally { ui.dom.window.close(); }
});

test("German is first and language switching preserves the entire unsaved editor", async () => {
  const ui = await createPanel();
  try {
    assert.equal(ui.panel.language, "de");
    assert.deepEqual(Array.from(ui.root.querySelector('[data-selector="language"]').selector.select.options,
      option => option.value), ["de", "en"]);
    ui.select("new-menu", "Wohnzimmer");
    ui.button("Untermenü hinzufügen").click();
    ui.button("Untermenü bearbeiten").click();
    ui.select("entity", "light.ceiling");
    ui.button("Entität hinzufügen").click();
    ui.select("new-menu", "Noch nicht hinzugefügt");
    ui.select("domain", "sensor");
    ui.select("entity", "sensor.temp");
    const before = JSON.stringify(ui.panel.model);
    ui.select("language", "en");
    assert.equal(ui.panel.getAttribute("lang"), "en");
    assert.equal(ui.panel.dirty, true);
    assert.equal(JSON.stringify(ui.panel.model), before);
    assert.equal(ui.panel.path.at(-1).label, "Wohnzimmer");
    assert.equal(ui.root.querySelector('[data-field="new-menu"]').value, "Noch nicht hinzugefügt");
    assert.equal(ui.root.querySelector('[data-selector="entity"]').value, "sensor.temp");
    assert.equal(ui.root.querySelector('[data-selector="domain"]').value, "sensor");
    assert.equal(ui.root.querySelector(".save-state").textContent, "Unsaved changes");
    assert.ok(ui.button("Save"));
    assert.ok(ui.button("Add entity"));
    assert.equal(ui.root.querySelector('[data-selector="domain"]').label, "Entity type");
    assert.equal(ui.dom.window.localStorage.getItem("enigmaha_companion.language"), "en");
    ui.button("Save").click();
    await tick();
    assert.equal(ui.saved().root.children[0].label, "Wohnzimmer");
    assert.equal(ui.saved().root.children[0].children[0].label, "Lampe <img src=x>");
    assert.equal(ui.root.querySelector(".notice").textContent,
      "Saved. The receiver menu will update on its next refresh.");
    ui.select("language", "de");
    assert.ok(ui.button("Speichern"));
    assert.equal(ui.panel.dirty, false);
    assert.match(ui.root.querySelector(".notice").textContent, /^Gespeichert/);
  } finally {ui.dom.window.close();}
});

test("language preference survives reopening and unsupported values fall back to German", async () => {
  for (const [savedLanguage, expected] of [["en", "en"], ["de", "de"], ["fr", "de"]]) {
    const ui = await createPanel({savedLanguage});
    try {
      assert.equal(ui.panel.language, expected);
      assert.equal(ui.panel.getAttribute("lang"), expected);
      assert.ok(ui.button(expected === "en" ? "Add entity" : "Entität hinzufügen"));
      ui.select("language", "fr");
      assert.equal(ui.panel.language, expected);
    } finally {ui.dom.window.close();}
  }
});

test("language selection still works when browser storage is blocked", async () => {
  const ui = await createPanel({blockedStorage: true});
  try {
    assert.equal(ui.panel.language, "de");
    ui.select("language", "en");
    assert.ok(ui.button("Save"));
  } finally {ui.dom.window.close();}
});

test("English editor translates errors, confirmation dialogs, counts and dynamic labels safely", async () => {
  const ui = await createPanel({savedLanguage: "en"});
  try {
    const name = "Wohnzimmer <img src=x> {count}";
    ui.select("new-menu", name);
    ui.button("Add submenu").click();
    assert.equal(ui.root.querySelector('[data-field^="label-"]').hint, "0 entries");
    ui.button("Edit submenu").click();
    assert.equal(ui.root.querySelector(".section-heading p").textContent, `Edit and sort entries in “${name}”.`);
    ui.select("entity", "light.ceiling");
    ui.button("Add entity").click();
    ui.root.querySelector(".breadcrumbs ha-button").click();
    assert.equal(ui.root.querySelector('[data-field^="label-"]').hint, "1 entry");
    ui.button("Remove").click();
    assert.equal(ui.root.querySelector("dialog h2").textContent, "Remove the submenu and all its entries?");
    assert.equal(ui.root.querySelector("dialog p").textContent,
      `“${name}” and all its entries will be removed from the receiver menu.`);
    assert.equal(ui.root.querySelector("img"), null);
    ui.button("Cancel").click();
    await tick();
    ui.fail();
    ui.button("Save").click();
    await tick();
    assert.match(ui.root.querySelector(".notice").textContent, /menu has changed/);
    assert.equal(ui.panel.dirty, true);
    ui.button("Reload").click();
    assert.equal(ui.root.querySelector("dialog h2").textContent, "Discard unsaved changes?");
    ui.button("Cancel").click();
    await tick();
    assert.equal(ui.panel.model.root.children[0].label, name);
  } finally {ui.dom.window.close();}
});

test("create nested menu, select entity, save through HA", async () => {
  const ui = await createPanel();
  try {
    ui.select("new-menu", "Wohnzimmer");
    ui.button("Untermenü hinzufügen").click();
    ui.button("Untermenü bearbeiten").click();
    ui.select("entity", "light.ceiling");
    ui.button("Entität hinzufügen").click();
    assert.equal(ui.panel.model.root.children[0].children[0].entity_id, "light.ceiling");
    assert.equal(ui.root.querySelector("img"), null, "Entity labels must not become HTML");
    ui.button("Speichern").click();
    await tick();
    assert.equal(ui.saved().root.children[0].label, "Wohnzimmer");
    assert.equal(ui.panel.model.revision, 2);
    assert.equal(ui.panel.path.at(-1).label, "Wohnzimmer");
    assert.equal(ui.panel.dirty, false);
  } finally {ui.dom.window.close();}
});

test("refresh preserves both scroll positions and submenu navigation resets the list", async () => {
  const ui = await createPanel();
  try {
    ui.select("new-menu", "Wohnzimmer");
    ui.button("Untermenü hinzufügen").click();
    ui.root.querySelector(".menu-column").scrollTop = 640;
    ui.root.querySelector(".tools-column").scrollTop = 180;
    ui.panel.render();
    assert.equal(ui.root.querySelector(".menu-column").scrollTop, 640);
    assert.equal(ui.root.querySelector(".tools-column").scrollTop, 180);
    ui.button("Untermenü bearbeiten").click();
    assert.equal(ui.root.querySelector(".menu-column").scrollTop, 0);
    assert.equal(ui.root.querySelector(".tools-column").scrollTop, 180);
  } finally {ui.dom.window.close();}
});

test("sensor selection produces read-only entry", async () => {
  const ui = await createPanel();
  try {
    ui.select("entity", "sensor.temp");
    ui.button("Entität hinzufügen").click();
    assert.equal(ui.panel.model.root.children[0].entity_id, "sensor.temp");
    assert.equal(ui.panel.model.root.children[0].actions.length, 0);
  } finally {ui.dom.window.close();}
});

test("ordering and removal update the saved menu", async () => {
  const ui = await createPanel();
  try {
    ui.select("entity", "light.ceiling");
    ui.button("Entität hinzufügen").click();
    ui.select("entity", "sensor.temp");
    ui.button("Entität hinzufügen").click();
    [...ui.root.querySelectorAll("ha-icon-button")].find(b => b.label === "Nach oben" && !b.disabled).click();
    assert.equal(ui.panel.model.root.children[0].entity_id, "sensor.temp");
    ui.button("Entfernen").click();
    assert.equal(ui.panel.model.root.children.length, 1);
    assert.equal(ui.panel.model.root.children[0].entity_id, "light.ceiling");
  } finally {ui.dom.window.close();}
});

test("stale save keeps unsaved edits", async () => {
  const ui = await createPanel();
  try {
    ui.select("entity", "light.ceiling");
    ui.button("Entität hinzufügen").click();
    ui.fail();
    ui.button("Speichern").click();
    await tick();
    assert.equal(ui.panel.dirty, true);
    assert.equal(ui.panel.model.root.children.length, 1);
    assert.match(ui.panel.message, /inzwischen geändert/);
  } finally {ui.dom.window.close();}
});

test("reload waits for the themed modal and cancellation preserves unsaved edits", async () => {
  const ui = await createPanel();
  try {
    ui.select("entity", "light.ceiling");
    ui.button("Entität hinzufügen").click();
    const model = ui.panel.model;
    ui.button("Neu laden").focus();
    ui.button("Neu laden").click();
    const dialog = ui.root.querySelector("dialog");
    assert.ok(dialog.open);
    assert.equal(dialog.querySelector("h2").textContent, "Ungespeicherte Änderungen verwerfen?");
    assert.equal(ui.requests.length, 1, "No reload before confirmation");
    await tick();
    assert.equal(ui.root.activeElement, ui.button("Abbrechen"));
    ui.button("Neu laden").click();
    ui.button("Speichern").click();
    assert.equal(ui.root.querySelectorAll("dialog").length, 1);
    assert.equal(ui.requests.length, 1);
    ui.button("Abbrechen").click();
    await tick();
    assert.equal(ui.root.querySelector("dialog"), null);
    assert.equal(ui.panel.model, model);
    assert.equal(ui.panel.dirty, true);
    assert.equal(ui.requests.length, 1);
    assert.equal(ui.root.activeElement, ui.button("Neu laden"));
    ui.button("Neu laden").click();
    const escape = new ui.dom.window.Event("cancel", {cancelable: true});
    ui.root.querySelector("dialog").dispatchEvent(escape);
    await tick();
    assert.equal(escape.defaultPrevented, true);
    assert.equal(ui.panel.model, model);
    assert.equal(ui.requests.length, 1);
    ui.button("Neu laden").click();
    const accept = ui.button("Verwerfen und neu laden");
    assert.equal(accept.getAttribute("variant"), "danger");
    accept.click();
    accept.click();
    await tick();
    assert.equal(ui.requests.length, 2, "Confirmation reloads exactly once");
    assert.equal(ui.panel.dirty, false);
    assert.equal(ui.panel.model.root.children.length, 0);
  } finally {ui.dom.window.close();}
});

test("nonempty submenu deletion is confirmed and does not rely on a stale row index", async () => {
  const ui = await createPanel();
  try {
    ui.select("new-menu", "Raum <img src=x>");
    ui.button("Untermenü hinzufügen").click();
    const submenu = ui.panel.model.root.children[0];
    submenu.children.push({type: "entity", id: "lamp", entity_id: "light.ceiling", label: "Lampe", actions: ["toggle"]});
    ui.panel.dirty = false;
    ui.panel.render();
    ui.button("Entfernen").click();
    assert.equal(ui.panel.model.root.children.length, 1);
    assert.equal(ui.panel.dirty, false);
    const dialog = ui.root.querySelector("dialog");
    assert.match(dialog.textContent, /Raum <img src=x>/);
    assert.equal(dialog.querySelector("img"), null);
    ui.panel.render();
    assert.equal(ui.root.querySelector("dialog"), dialog, "Rerender preserves the open modal");
    assert.ok(dialog.open);
    dialog.close();
    await tick();
    assert.equal(ui.panel.model.root.children[0], submenu);
    assert.equal(submenu.children.length, 1);
    assert.equal(ui.panel.dirty, false);
    ui.button("Entfernen").click();
    // Resolve against the current position, even if the model was reordered.
    const sibling = {type: "menu", id: "other", label: "Anderer Raum", children: []};
    ui.panel.model.root.children.unshift(sibling);
    ui.button("Untermenü entfernen").click();
    await tick();
    assert.equal(ui.panel.model.root.children.length, 1);
    assert.equal(ui.panel.model.root.children[0], sibling);
    assert.equal(ui.panel.dirty, true);
    assert.equal(ui.requests.length, 1, "Deletion is saved only by the save action");
  } finally {ui.dom.window.close();}
});

test("leaving the panel cancels an outstanding confirmation", async () => {
  const ui = await createPanel();
  try {
    ui.select("entity", "light.ceiling");
    ui.button("Entität hinzufügen").click();
    const model = ui.panel.model;
    ui.button("Neu laden").click();
    const accept = ui.button("Verwerfen und neu laden");
    ui.panel.remove();
    accept.click();
    await tick();
    assert.equal(ui.panel.confirmation, undefined);
    assert.equal(ui.root.querySelector("dialog"), null);
    assert.equal(ui.panel.model, model);
    assert.equal(ui.panel.dirty, true);
    assert.equal(ui.requests.length, 1);
  } finally {ui.dom.window.close();}
});

test("native selector is loaded on first visit without a previous HA editor", async () => {
  const ui = await createPanel({lazySelectors: true});
  try {
    assert.equal(ui.loads(), 1);
    const picker = ui.root.querySelector('[data-selector="entity"]');
    assert.equal(picker.localName, "ha-selector");
    assert.equal(picker.selector.entity.multiple, false);
    assert.equal(picker.hass, ui.panel._hass);
    assert.ok(ui.button("Entität hinzufügen").disabled);
    assert.deepEqual(ui.requests, ["enigmaha_companion/v1/config"]);
  } finally {ui.dom.window.close();}
});

test("domain, class and inherited area filters combine and reject stale selection", async () => {
  const ui = await createPanel();
  try {
    ui.select("entity", "light.ceiling");
    assert.equal(ui.button("Entität hinzufügen").disabled, false);
    ui.select("domain", "sensor");
    assert.equal(ui.button("Entität hinzufügen").disabled, true);
    ui.select("device_class", "temperature");
    ui.select("area", "living");
    const definition = ui.root.querySelector('[data-selector="entity"]').selector.entity;
    assert.equal(definition.filter.domain, "sensor");
    assert.equal(definition.filter.device_class, "temperature");
    assert.deepEqual(Array.from(definition.include_entities), ["light.ceiling", "sensor.temp"]);
    ui.select("entity", "sensor.power");
    assert.ok(ui.button("Entität hinzufügen").disabled);
    ui.select("entity", "sensor.temp");
    ui.button("Entität hinzufügen").click();
    assert.equal(ui.panel.model.root.children[0].entity_id, "sensor.temp");
    ui.button("Filter zurücksetzen").click();
    assert.equal(ui.panel.model.root.children.length, 1);
    assert.equal(ui.root.querySelector('[data-selector="entity"]').selector.entity.filter, undefined);
  } finally {ui.dom.window.close();}
});

test("empty area returns an empty allow-list and cannot add an entity", async () => {
  const ui = await createPanel();
  try {
    ui.select("area", "empty-area");
    assert.equal(ui.root.querySelector('[data-selector="entity"]').selector.entity.include_entities.length, 0);
    ui.select("entity", "light.ceiling");
    assert.ok(ui.button("Entität hinzufügen").disabled);
  } finally {ui.dom.window.close();}
});

test("HA updates propagate without destroying selectors and clear deleted entities", async () => {
  const ui = await createPanel();
  try {
    ui.select("entity", "light.ceiling");
    const picker = ui.root.querySelector('[data-selector="entity"]');
    const next = {...ui.panel._hass, states: {...ui.panel._hass.states}};
    delete next.states["light.ceiling"];
    ui.panel.hass = next;
    assert.equal(ui.root.querySelector('[data-selector="entity"]'), picker);
    assert.equal(picker.hass, next);
    assert.ok(ui.button("Entität hinzufügen").disabled);
  } finally {ui.dom.window.close();}
});

test("failed HA component loading displays an error instead of an inert selector", async () => {
  const ui = await createPanel({brokenSelectors: true});
  try {
    assert.equal(ui.panel.loading, false);
    assert.match(ui.panel.message, /Editor konnte nicht geladen/);
    assert.equal(ui.root.querySelector('[data-selector="entity"]'), null);
  } finally {ui.dom.window.close();}
});


test("native form edits and appearance dropdowns persist values without replacing focused fields", async () => {
  const ui = await createPanel();
  try {
    assert.equal(ui.button("Speichern").disabled, true);
    const title = ui.root.querySelector('[data-field="menu-title"]');
    const size = ui.root.querySelector('[data-selector="font-size"]');
    const font = ui.root.querySelector('[data-selector="font-family"]');
    assert.equal(size.localName, "ha-selector");
    assert.equal(size.selector.select.mode, "dropdown");
    assert.equal(size.required, true);
    assert.equal(size.value, "28");
    assert.equal(size.selector.select.options[0].value, "16");
    assert.equal(size.selector.select.options.at(-1).value, "64");
    assert.equal(font.selector.select.mode, "dropdown");
    assert.equal(font.required, true);
    ui.select("menu-title", "Mein Zuhause");
    ui.select("font-family", "Fixed");
    ui.select("font-size", "36");
    assert.equal(ui.root.querySelector('[data-field="menu-title"]'), title);
    assert.equal(ui.button("Speichern").disabled, false);
    assert.equal(ui.root.querySelector(".save-state").textContent, "Ungespeicherte Änderungen");
    ui.select("entity", "light.ceiling");
    ui.button("Entität hinzufügen").click();
    const node = ui.panel.model.root.children[0];
    ui.select("label-" + node.id, "Deckenlicht");
    assert.equal(ui.root.querySelector('[data-selector^="toggle-"]'), null);
    ui.button("Speichern").click();
    await tick();
    assert.equal(ui.saved().root.label, "Mein Zuhause");
    assert.equal(ui.saved().display.font_size, 36);
    assert.equal(ui.saved().display.font_family, "Fixed");
    assert.equal(ui.saved().root.children[0].label, "Deckenlicht");
    assert.deepEqual(ui.saved().root.children[0].actions, ["toggle"]);
    assert.equal(ui.button("Speichern").disabled, true);
  } finally {ui.dom.window.close();}
});

test("appearance dropdowns retain custom saved fonts and reject empty or invalid choices", async () => {
  const ui = await createPanel();
  try {
    ui.panel.model.display = {font_family: "MySkinFont", font_size: 31};
    ui.panel.render();
    const font = ui.root.querySelector('[data-selector="font-family"]');
    const size = ui.root.querySelector('[data-selector="font-size"]');
    assert.equal(font.value, "MySkinFont");
    assert.ok(font.selector.select.options.some(option => option.value === "MySkinFont"));
    assert.equal(size.value, "31");
    for (const value of [undefined, "", "15", "65", "31.5", "abc"]) ui.select("font-size", value);
    for (const value of [undefined, "", "unlisted font"]) ui.select("font-family", value);
    assert.equal(ui.panel.model.display.font_family, "MySkinFont");
    assert.equal(ui.panel.model.display.font_size, 31);
    assert.equal(font.value, "MySkinFont");
    assert.equal(size.value, "31");
    assert.equal(ui.panel.dirty, false);
    ui.select("font-size", "16");
    assert.equal(ui.panel.model.display.font_size, 16);
    ui.select("font-size", "64");
    ui.select("font-size", undefined);
    assert.equal(ui.panel.model.display.font_size, 64);
    assert.equal(size.value, "64");
    ui.select("font-family", "Regular");
    ui.select("font-family", undefined);
    assert.equal(font.value, "Regular");
    ui.button("Speichern").click();
    await tick();
    assert.equal(ui.saved().display.font_family, "Regular");
    assert.equal(ui.saved().display.font_size, 64);
  } finally {ui.dom.window.close();}
});

test("filter changes preserve the submenu draft and breadcrumb navigation returns to parent", async () => {
  const ui = await createPanel();
  try {
    assert.equal(ui.button("Untermenü hinzufügen").disabled, true);
    ui.select("new-menu", "   ");
    assert.equal(ui.button("Untermenü hinzufügen").disabled, true);
    ui.select("new-menu", "Wohnzimmer");
    assert.equal(ui.button("Untermenü hinzufügen").disabled, false);
    ui.select("domain", "sensor");
    assert.equal(ui.root.querySelector('[data-field="new-menu"]').value, "Wohnzimmer");
    ui.button("Untermenü hinzufügen").click();
    assert.equal(ui.button("Untermenü hinzufügen").disabled, true);
    ui.button("Untermenü bearbeiten").click();
    assert.equal(ui.root.querySelector('[aria-current="page"]').textContent, "Wohnzimmer");
    ui.button("Home Assistant").click();
    assert.equal(ui.panel.path.length, 1);
  } finally {ui.dom.window.close();}
});

test("saving disables native controls and duplicate actions", async () => {
  const ui = await createPanel();
  try {
    ui.select("entity", "sensor.temp");
    ui.button("Entität hinzufügen").click();
    let finish;
    let writes = 0;
    ui.panel._hass.callApi = () => { writes++; return new Promise(resolve => { finish = resolve; }); };
    ui.button("Speichern").click();
    assert.equal(ui.panel.loading, true);
    for (const control of ui.root.querySelectorAll("ha-button, ha-icon-button, ha-selector, ha-input")) {
      assert.equal(control.disabled, true);
    }
    ui.button("Speichern").click();
    ui.select("menu-title", "Blocked");
    assert.equal(writes, 1);
    assert.equal(ui.panel.model.root.label, "Home Assistant");
    finish(ui.panel.model);
    await tick();
    assert.equal(ui.panel.loading, false);
  } finally {ui.dom.window.close();}
});


test("entity icons and native field hints follow HA updates without replacing the name field", async () => {
  const ui = await createPanel();
  try {
    ui.select("entity", "light.ceiling");
    ui.button("Entität hinzufügen").click();
    const field = ui.root.querySelector('ha-input[data-entity-id="light.ceiling"]');
    const icon = ui.root.querySelector('ha-state-icon[data-entity-id="light.ceiling"]');
    assert.equal(field.hint, "Lampe <img src=x> (light.ceiling)");
    assert.equal(icon.stateObj, ui.panel._hass.states["light.ceiling"]);
    const state = {...icon.stateObj, attributes: {friendly_name: "Deckenlampe", icon: "mdi:ceiling-light"}};
    ui.panel.hass = {...ui.panel._hass, states: {...ui.panel._hass.states, "light.ceiling": state}};
    assert.equal(ui.root.querySelector('ha-input[data-entity-id="light.ceiling"]'), field);
    assert.equal(field.hint, "Deckenlampe (light.ceiling)");
    assert.equal(icon.stateObj, state);
    assert.equal(icon.icon, "mdi:ceiling-light");
    ui.panel.hass = {...ui.panel._hass, entities: {...ui.panel._hass.entities,
      "light.ceiling": {icon: "mdi:lightbulb-outline"}}};
    assert.equal(icon.icon, "mdi:lightbulb-outline");
    const next = {...ui.panel._hass, states: {...ui.panel._hass.states}, entities: {}};
    delete next.states["light.ceiling"];
    ui.panel.hass = next;
    assert.equal(field.hint, "(light.ceiling)");
    assert.equal(icon.icon, undefined);
    assert.equal(icon.stateObj.entity_id, "light.ceiling");
    assert.equal(icon.stateObj.state, "unknown");
    assert.equal(ui.root.querySelector("img"), null);
    assert.equal(ui.panel.model.root.children[0].label, "Lampe <img src=x>");
  } finally {ui.dom.window.close();}
});

test("saving derives supported receiver actions throughout nested menus without changing the draft on failure", async () => {
  const ui = await createPanel();
  try {
    const entries = ["light.ceiling", "switch.socket", "input_boolean.helper", "sensor.temp", "binary_sensor.window"]
      .map((id, index) => ({type: "entity", id: "entry-" + index, label: id, entity_id: id, actions: []}));
    ui.panel.model.root.children.push({type: "menu", id: "nested", label: "Raum", children: entries});
    ui.panel.markDirty();
    ui.panel.render();
    const buttons = [...ui.root.querySelectorAll(".entry-actions ha-icon-button")];
    assert.deepEqual(buttons.map(b => b.label), ["Untermenü bearbeiten", "Nach oben", "Nach unten", "Entfernen"]);
    assert.equal(buttons[0].querySelector("ha-icon").icon, "mdi:pencil");
    ui.fail();
    await ui.panel.save();
    assert.equal(ui.panel.dirty, true);
    assert.equal(entries[0].actions.length, 0);
    let sent;
    ui.panel._hass.callApi = async (_method, _route, body) => {
      sent = JSON.parse(JSON.stringify(body));
      return {...sent, revision: sent.revision + 1};
    };
    await ui.panel.save();
    assert.deepEqual(sent.root.children[0].children.map(n => n.actions),
      [["toggle"], ["toggle"], ["toggle"], [], []]);
  } finally {ui.dom.window.close();}
});


test("new entities and submenus are revealed in the current menu after rendering", async () => {
  const ui = await createPanel();
  try {
    ui.select("entity", "light.ceiling");
    ui.button("Entität hinzufügen").click();
    await tick();
    assert.equal(ui.scrolled.at(-1).row.dataset.nodeId, ui.panel.model.root.children.at(-1).id);
    assert.equal(ui.scrolled.at(-1).row.isConnected, true);
    assert.equal(ui.scrolled.at(-1).row.classList.contains("revealed"), true);
    assert.equal(ui.scrolled.at(-1).options.block, "center");
    assert.equal(ui.scrolled.at(-1).options.behavior, "smooth");
    ui.select("new-menu", "Wohnzimmer");
    ui.button("Untermenü hinzufügen").click();
    await tick();
    const submenu = ui.panel.model.root.children.at(-1);
    assert.equal(ui.scrolled.at(-1).row.dataset.nodeId, submenu.id);
    ui.button("Untermenü bearbeiten").click();
    const matchMedia = ui.dom.window.matchMedia;
    ui.dom.window.matchMedia = query => query.includes("prefers-reduced-motion") ? {matches: true} : matchMedia(query);
    ui.select("entity", "sensor.temp");
    ui.button("Entität hinzufügen").click();
    await tick();
    assert.equal(ui.scrolled.at(-1).row.dataset.nodeId, submenu.children[0].id);
    assert.equal(ui.scrolled.at(-1).options.behavior, "auto");
    const count = ui.scrolled.length;
    ui.button("Untermenü hinzufügen").click();
    await tick();
    assert.equal(ui.scrolled.length, count, "an empty submenu must not trigger scrolling");
  } finally {ui.dom.window.close();}
});

test("a pending reveal never scrolls a row removed by navigation", async () => {
  const ui = await createPanel();
  try {
    ui.select("entity", "light.ceiling");
    ui.button("Entität hinzufügen").click();
    ui.panel.render();
    await tick();
    assert.equal(ui.scrolled.length, 0);
  } finally {ui.dom.window.close();}
});

test("HA drag-and-drop sorts entries after drag-end and saves submenu contents intact", async () => {
  const ui = await createPanel();
  try {
    const items = ui.panel.model.root.children;
    items.push({type: "menu", id: "room", label: "Raum", children: [
      {type: "entity", id: "nested", label: "Temperatur", entity_id: "sensor.temp", actions: []}]},
      {type: "entity", id: "light", label: "Licht", entity_id: "light.ceiling", actions: ["toggle"]},
      {type: "entity", id: "power", label: "Leistung", entity_id: "sensor.power", actions: []});
    ui.panel.render();
    const reorder = async (oldIndex, newIndex) => {
      const sortable = ui.root.querySelector("ha-sortable");
      assert.equal(sortable.handleSelector, ".drag-handle");
      assert.equal(sortable.draggableSelector, ".row");
      sortable.dispatchEvent(new ui.dom.window.CustomEvent("item-moved", {detail: {oldIndex, newIndex}}));
      assert.equal(ui.root.querySelector("ha-sortable"), sortable, "keep the sortable alive until drag-end");
      sortable.dispatchEvent(new ui.dom.window.CustomEvent("drag-end"));
      await tick();
    };
    await reorder(0, 2);
    assert.deepEqual(Array.from(items, n => n.id), ["light", "power", "room"]);
    assert.equal(items[2].children[0].id, "nested");
    assert.equal(ui.panel.dirty, true);
    assert.equal(ui.scrolled.at(-1).row.dataset.nodeId, "room");
    await reorder(2, 0);
    assert.deepEqual(Array.from(items, n => n.id), ["room", "light", "power"]);
    ui.button("Speichern").click();
    await tick();
    assert.deepEqual(ui.saved().root.children.map(n => n.id), ["room", "light", "power"]);
    assert.equal(ui.saved().root.children[0].children[0].entity_id, "sensor.temp");
  } finally {ui.dom.window.close();}
});

test("cancelled, invalid and stale drag operations leave the menu unchanged", async () => {
  const ui = await createPanel();
  try {
    const items = ui.panel.model.root.children;
    items.push({type: "menu", id: "first", label: "Erstes", children: []},
      {type: "menu", id: "second", label: "Zweites", children: []});
    ui.panel.render();
    let sortable = ui.root.querySelector("ha-sortable");
    sortable.dispatchEvent(new ui.dom.window.CustomEvent("drag-end"));
    for (const detail of [{oldIndex: -1, newIndex: 0}, {oldIndex: 0, newIndex: 2},
      {oldIndex: 0.5, newIndex: 1}, {oldIndex: 0, newIndex: 0}]) {
      sortable.dispatchEvent(new ui.dom.window.CustomEvent("item-moved", {detail}));
      sortable.dispatchEvent(new ui.dom.window.CustomEvent("drag-end"));
      await tick();
    }
    assert.equal(ui.panel.dirty, false);
    assert.deepEqual(Array.from(items, n => n.id), ["first", "second"]);
    sortable.dispatchEvent(new ui.dom.window.CustomEvent("item-moved", {detail: {oldIndex: 0, newIndex: 1}}));
    sortable.dispatchEvent(new ui.dom.window.CustomEvent("drag-end"));
    ui.panel.path.push(items[0]);
    ui.panel.render();
    await tick();
    assert.deepEqual(Array.from(items, n => n.id), ["first", "second"]);
    assert.equal(ui.panel.dirty, false);
    ui.panel.path.pop();
    ui.panel.loading = true;
    ui.panel.render();
    sortable = ui.root.querySelector("ha-sortable");
    assert.equal(sortable.disabled, true);
    sortable.dispatchEvent(new ui.dom.window.CustomEvent("item-moved", {detail: {oldIndex: 0, newIndex: 1}}));
    sortable.dispatchEvent(new ui.dom.window.CustomEvent("drag-end"));
    await tick();
    assert.deepEqual(Array.from(items, n => n.id), ["first", "second"]);
  } finally {ui.dom.window.close();}
});

test("HA sortable is loaded even if selectors were already registered", async () => {
  const ui = await createPanel({lazySortable: true});
  try {
    assert.equal(ui.loads(), 1);
    assert.ok(ui.dom.window.customElements.get("ha-sortable"));
    assert.equal(ui.panel.selectorsReady, true);
  } finally {ui.dom.window.close();}
});

test("edge scrolling uses the current responsive viewport and stops on cancellation, refresh or disconnect", async () => {
  const ui = await createPanel();
  try {
    const frames = new Map();
    let id = 0;
    ui.dom.window.requestAnimationFrame = callback => { frames.set(++id, callback); return id; };
    ui.dom.window.cancelAnimationFrame = key => frames.delete(key);
    const advance = time => { const callbacks = [...frames.values()]; frames.clear(); callbacks.forEach(fn => fn(time)); };
    const scroller = ui.root.querySelector(".menu-column");
    const sortable = ui.root.querySelector("ha-sortable");
    const rect = (top, bottom) => ({top, bottom, left: 0, right: 600, width: 600, height: bottom - top});
    scroller.getBoundingClientRect = () => rect(100, 500);
    ui.panel.getBoundingClientRect = () => rect(0, 800);
    sortable.getBoundingClientRect = () => rect(100, 1800);
    ui.root.querySelector("header").getBoundingClientRect = () => rect(0, 64);
    Object.defineProperties(scroller, {clientHeight: {value: 400}, scrollHeight: {value: 1600}});
    Object.defineProperties(ui.panel, {clientHeight: {value: 800}, scrollHeight: {value: 2000}});
    assert.equal(sortable.options.scroll, false, "avoid competing library scrolling");
    const pointer = (x, y) => ui.dom.window.document.dispatchEvent(new ui.dom.window.MouseEvent("pointermove", {clientX: x, clientY: y}));
    sortable.dispatchEvent(new ui.dom.window.Event("drag-start"));
    pointer(20, 495);
    advance(0);
    assert.ok(scroller.scrollTop > 0);
    assert.equal(ui.panel.scrollTop, 0);
    const desktop = scroller.scrollTop;
    ui.layoutMedia.matches = true;
    pointer(20, 795);
    advance(16);
    assert.ok(ui.panel.scrollTop > 0, "a breakpoint change during dragging changes the scroll target");
    assert.equal(scroller.scrollTop, desktop);
    const mobile = ui.panel.scrollTop;
    pointer(700, 795);
    advance(32);
    assert.equal(ui.panel.scrollTop, mobile, "outside the list width must not scroll");
    ui.dom.window.document.dispatchEvent(new ui.dom.window.Event("pointercancel"));
    assert.equal(frames.size, 0);
    ui.layoutMedia.matches = false;
    sortable.dispatchEvent(new ui.dom.window.Event("drag-start"));
    scroller.scrollTop = 1199;
    pointer(20, 495);
    advance(48);
    assert.equal(scroller.scrollTop, 1200, "stop at the bottom of the list");
    scroller.scrollTop = 1;
    pointer(20, 105);
    advance(64);
    assert.equal(scroller.scrollTop, 0, "stop at the top of the list");
    ui.panel.render();
    assert.equal(frames.size, 0, "refresh stops the old drag loop");
    ui.root.querySelector("ha-sortable").dispatchEvent(new ui.dom.window.Event("drag-start"));
    ui.panel.remove();
    assert.equal(frames.size, 0, "leaving the panel stops scrolling");
  } finally {ui.dom.window.close();}
});

test("native SortableJS drag scrolls across the shadow boundary at both edges until drop", async () => {
  const ui = await createPanel();
  let instance;
  try {
    ui.panel.model.root.children = Array.from({length: 20}, (_, i) => ({type: "menu", id: "row" + i, label: "Raum " + i, children: []}));
    ui.panel.render();
    const scroller = ui.root.querySelector(".menu-column");
    const tools = ui.root.querySelector(".tools-column");
    const sortable = ui.root.querySelector("ha-sortable");
    const list = ui.root.querySelector(".entry-list");
    scroller.style.overflowY = "auto";
    scroller.getBoundingClientRect = () => ({top: 100, bottom: 500, left: 0, right: 600, width: 600, height: 400});
    Object.defineProperties(scroller, {clientHeight: {value: 400}, scrollHeight: {value: 1600},
      clientWidth: {value: 600}, scrollWidth: {value: 600}});
    list.getBoundingClientRect = () => ({top: 100 - scroller.scrollTop, bottom: 1700 - scroller.scrollTop, left: 0, right: 600, width: 600, height: 1600});
    const row = list.firstElementChild;
    row.getBoundingClientRect = () => ({top: 120, bottom: 180, left: 0, right: 600, width: 600, height: 60});
    // Browser hit testing from the document sees the custom-panel host, not its
    // shadow descendants. This is the failure case for automatic parent detection.
    ui.dom.window.document.elementFromPoint = () => ui.panel;
    ui.dom.window.requestAnimationFrame = callback => ui.dom.window.setTimeout(() => callback(ui.dom.window.performance.now()), 16);
    ui.dom.window.cancelAnimationFrame = id => ui.dom.window.clearTimeout(id);
    ui.dom.window.eval(fs.readFileSync(dependencyRequire.resolve("sortablejs"), "utf8"));
    instance = new ui.dom.window.Sortable(list, {...sortable.options, supportPointer: false,
      handle: sortable.handleSelector, draggable: sortable.draggableSelector,
      onStart: () => sortable.dispatchEvent(new ui.dom.window.Event("drag-start")),
      onEnd: () => sortable.dispatchEvent(new ui.dom.window.Event("drag-end"))});
    row.querySelector(".drag-handle").dispatchEvent(new ui.dom.window.MouseEvent("mousedown", {
      bubbles: true, composed: true, cancelable: true, button: 0, clientX: 20, clientY: 150}));
    const start = new ui.dom.window.MouseEvent("dragstart", {bubbles: true, composed: true, cancelable: true, clientX: 20, clientY: 150});
    Object.defineProperty(start, "dataTransfer", {value: {setData() {}}});
    row.dispatchEvent(start);
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.ok(ui.dom.window.Sortable.active, "a native drag session is active");
    const over = y => ui.dom.window.document.dispatchEvent(new ui.dom.window.MouseEvent("dragover", {
      bubbles: true, clientX: 20, clientY: y}));
    const advance = () => new Promise(resolve => setTimeout(resolve, 120));
    over(490);
    await advance();
    assert.ok(scroller.scrollTop > 0, "holding at the bottom scrolls down");
    const down = scroller.scrollTop;
    await advance();
    assert.ok(scroller.scrollTop > down, "scrolling continues without pointer movement");
    scroller.scrollTop = 600;
    over(110);
    await advance();
    assert.ok(scroller.scrollTop < 600, "holding at the top scrolls up");
    over(300);
    await advance();
    const middle = scroller.scrollTop;
    await advance();
    assert.equal(scroller.scrollTop, middle, "leaving the edge stops scrolling");
    over(490);
    await advance();
    ui.dom.window.document.dispatchEvent(new ui.dom.window.Event("drop", {bubbles: true}));
    const dropped = scroller.scrollTop;
    await advance();
    assert.equal(scroller.scrollTop, dropped, "drop stops scrolling");
    assert.equal(tools.scrollTop, 0, "the settings column never scrolls with the list");
    assert.equal(ui.panel.scrollTop, 0);
  } finally {instance?.destroy(); ui.dom.window.close();}
});
