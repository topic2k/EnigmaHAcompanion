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
  savedLanguage, integrationLanguage, haLanguage, haLocale, browserLanguages,
  blockedStorage = false, hassBeforeConnect = false, overview = false, callWS} = {}) {
  const dom = new JSDOM("<!doctype html><body></body>", {url: "http://ha.test", runScripts: "outside-only"});
  if (browserLanguages !== undefined) {
    Object.defineProperty(dom.window.navigator, "languages", {configurable: true, value: browserLanguages});
    Object.defineProperty(dom.window.navigator, "language", {configurable: true, value: browserLanguages[0] || ""});
  }
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
  const notifications = [];
  dom.window.document.addEventListener("hass-notification", event => notifications.push(event));
  let failSave = false;
  const model = {schema_version: 2, revision: 1, display: {font_family: "Regular", font_size: 28},
    menus: [{type: "menu", id: "home", label: "Home Assistant", children: [], access: {mode: "all"}}]};
  const requests = [];
  const compatibilityRequests = [];
  panel.hass = {
    language: haLanguage,
    locale: {language: haLocale},
    callWS,
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
      return {version: "1.0.0", receivers: [], editor_language: integrationLanguage};
    }
    if (route.endsWith("/users")) return {users: [{id: "anna", name: "Anna"}, {id: "ben", name: "Ben"}]};
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
  // Existing entry-editor cases enter through the new overview's pencil action.
  if (!overview) button(panel.t("Menüeinträge bearbeiten"))?.click();
  const select = (name, value) => {
    const control = root.querySelector(`[data-selector="${name}"], [data-field="${name}"]`);
    if (control.localName === "ha-input") {
      control.value = String(value ?? "");
      control.dispatchEvent(new dom.window.Event("input", {bubbles: true, composed: true}));
    } else control.dispatchEvent(
      new dom.window.CustomEvent("value-changed", {detail: {value}, bubbles: true, composed: true}));
  };
  const renameMenu = value => {
    const id = panel.model.root.id;
    const editing = panel.view === "entries";
    if (editing) button(panel.t("Zur Menüverwaltung")).click();
    select("menu-label-" + id, value);
    if (editing) root.querySelector(`[data-edit-menu="${id}"]`).click();
  };
  const setIntegrationLanguage = async language => {
    integrationLanguage = language;
    await panel.loadEditorPreferences();
  };
  return {dom, panel, root, button, select, requests, notifications, compatibilityRequests, scrolled, layoutMedia,
    setIntegrationLanguage, renameMenu, loads: () => loads, saved: () => saved, fail: () => {failSave = true;}};
}

test("editor shows no notifications or update controls for any receiver or update status", async () => {
  const ui = await createPanel();
  try {
    ui.select("new-menu", "Wohnzimmer");
    ui.button("Untermenü hinzufügen").click();
    const field = ui.root.querySelector('[data-field="menu-label"]');
    const draft = JSON.stringify(ui.panel.model);
    for (const phase of [null, "ha_installing", "receivers", "ha_restart_required", "failed", "completed", "cancelled"]) {
      ui.panel._hass.callApi = async () => ({version: "1.0.0", protocol_version: 1, editor_language: "de",
        receivers: ["compatible", "version_mismatch", "protocol_mismatch", "unidentified_peer"].map(status => ({
          id: status, address: "192.0.2.1", version: "0.9.0", protocol_version: 2, status})),
        updates: {hacs: {entity_id: "update.enigmaha"}, candidate: {id: "candidate", release: {version: "2.0.0"}},
          job: phase && {id: "job", release: {version: "2.0.0"}, phase, error: "ha_restart_failed",
            receivers: [{address: "192.0.2.1", status: "failed"}]}}});
      await ui.panel.loadEditorPreferences();
      assert.equal(ui.root.querySelector('[data-field="menu-label"]'), field);
      assert.equal(JSON.stringify(ui.panel.model), draft);
      assert.equal(ui.panel.dirty, true);
      assert.equal(ui.notifications.length, 0);
      assert.equal(ui.root.querySelector(".compatibility, .release-link, a[href='/config/repairs']"), null);
      for (const label of ["Auf Updates prüfen", "Beide auf 2.0.0 aktualisieren",
        "Home Assistant neu starten", "Fehlgeschlagene Schritte erneut anbieten"]) {
        assert.equal(ui.button(label), undefined);
      }
    }
    ui.panel._hass.callApi = async () => { throw new Error("offline"); };
    await ui.panel.loadEditorPreferences();
    ui.panel.setLanguage("en");
    assert.equal(ui.notifications.length, 0);
    assert.equal(ui.root.querySelector(".compatibility, .notice, .save-state"), null);
    ui.panel.remove();
    let requests = 0;
    ui.panel._hass.callApi = async () => { requests++; };
    await ui.panel.loadEditorPreferences();
    assert.equal(requests, 0);
  } finally { ui.dom.window.close(); }
});

test("initial HA assignment before connection loads the editor without another state update", async () => {
  const ui = await createPanel({hassBeforeConnect: true});
  try {
    assert.equal(ui.requests.length, 1);
    assert.equal(ui.panel.model.root.label, "Home Assistant");
    assert.equal(ui.root.querySelector("[data-selector='language']"), null);
  } finally { ui.dom.window.close(); }
});

test("integration language switching preserves the entire unsaved editor", async () => {
  const ui = await createPanel();
  try {
    assert.equal(ui.panel.language, "de");
    assert.equal(ui.root.querySelector('[data-selector="language"]'), null);
    ui.select("new-menu", "Wohnzimmer");
    ui.button("Untermenü hinzufügen").click();
    ui.button("Untermenü bearbeiten").click();
    ui.select("entity", "light.ceiling");
    ui.button("Entität hinzufügen").click();
    ui.select("new-menu", "Noch nicht hinzugefügt");
    ui.select("domain", "sensor");
    ui.select("entity", "sensor.temp");
    const before = JSON.stringify(ui.panel.model);
    await ui.setIntegrationLanguage("en");
    assert.equal(ui.panel.getAttribute("lang"), "en");
    assert.equal(ui.panel.dirty, true);
    assert.equal(JSON.stringify(ui.panel.model), before);
    assert.equal(ui.panel.path.at(-1).label, "Wohnzimmer");
    assert.equal(ui.root.querySelector('[data-field="new-menu"]').value, "Noch nicht hinzugefügt");
    assert.equal(ui.root.querySelector('[data-selector="entity"]').value, "sensor.temp");
    assert.equal(ui.root.querySelector('[data-selector="domain"]').value, "sensor");
    assert.equal(ui.root.querySelector(".save-state"), null);
    assert.ok(ui.button("Save"));
    assert.ok(ui.button("Add entity"));
    assert.equal(ui.root.querySelector('[data-selector="domain"]').label, "Entity type");
    assert.equal(ui.dom.window.localStorage.getItem("enigmaha_companion.language"), null);
    ui.button("Save").click();
    await tick();
    assert.equal(ui.saved().menus[0].children[0].label, "Wohnzimmer");
    assert.equal(ui.saved().menus[0].children[0].children[0].label, "Lampe <img src=x>");
    assert.equal(ui.root.querySelector(".notice"), null);
    assert.equal(ui.notifications.length, 0);
    await ui.setIntegrationLanguage("de");
    assert.ok(ui.button("Speichern"));
    assert.equal(ui.panel.dirty, false);
    assert.equal(ui.root.querySelector(".notice"), null);
  } finally {ui.dom.window.close();}
});

test("legacy browser language is retained until an integration language is configured", async () => {
  for (const [savedLanguage, integrationLanguage, expected] of [
    ["en", undefined, "en"], ["de", undefined, "de"], ["fr", undefined, "de"],
    ["en", "de", "de"], ["de", "en", "en"], ["en", "fr", "en"],
  ]) {
    const ui = await createPanel({savedLanguage, integrationLanguage});
    try {
      assert.equal(ui.panel.language, expected);
      assert.equal(ui.panel.getAttribute("lang"), expected);
      assert.ok(ui.button(expected === "en" ? "Add entity" : "Entität hinzufügen"));
      await ui.setIntegrationLanguage("fr");
      assert.equal(ui.panel.language, expected);
      assert.equal(ui.dom.window.localStorage.getItem("enigmaha_companion.language"), savedLanguage);
    } finally {ui.dom.window.close();}
  }
});

test("integration language works on reopening and when browser storage is blocked", async () => {
  const ui = await createPanel({blockedStorage: true});
  try {
    assert.equal(ui.panel.language, "de");
    await ui.setIntegrationLanguage("en");
    assert.ok(ui.button("Save"));
  } finally {ui.dom.window.close();}
  const reopened = await createPanel({blockedStorage: true, integrationLanguage: "en"});
  try {
    assert.equal(reopened.panel.language, "en");
    assert.ok(reopened.button("Save"));
  } finally {reopened.dom.window.close();}
});

test("automatic language prefers HA, then browser locales, with German fallback", async () => {
  for (const [haLanguage, haLocale, browserLanguages, expected] of [
    ["de-DE", "en", ["en-US"], "de"],
    ["EN_gb", undefined, ["de"], "en"],
    [undefined, "en-GB", ["de"], "en"],
    [undefined, undefined, ["fr-FR", "en-US"], "en"],
    ["fr", undefined, ["de-AT", "en"], "de"],
    ["fr", undefined, ["fr-FR"], "de"],
    [undefined, undefined, [], "de"],
  ]) {
    const ui = await createPanel({integrationLanguage: "auto", savedLanguage: "en",
      haLanguage, haLocale, browserLanguages});
    try {
      assert.equal(ui.panel.languagePreference, "auto");
      assert.equal(ui.panel.language, expected);
      assert.equal(ui.panel.getAttribute("lang"), expected);
      assert.equal(ui.dom.window.localStorage.getItem("enigmaha_companion.language"), "en");
    } finally { ui.dom.window.close(); }
  }
});

test("automatic language follows HA and browser changes without losing unsaved drafts", async () => {
  const ui = await createPanel({integrationLanguage: "auto", haLanguage: "de", browserLanguages: ["en"]});
  try {
    ui.select("entity", "sensor.temp");
    ui.button("Entität hinzufügen").click();
    ui.select("new-menu", "Unfertiger Entwurf");
    const model = JSON.stringify(ui.panel.model);
    ui.panel.hass = {...ui.panel._hass, language: "en-US"};
    assert.equal(ui.panel.language, "en");
    assert.equal(ui.panel.dirty, true);
    assert.equal(JSON.stringify(ui.panel.model), model);
    assert.equal(ui.root.querySelector('[data-field="new-menu"]').value, "Unfertiger Entwurf");
    ui.panel.hass = {...ui.panel._hass, language: undefined};
    Object.defineProperty(ui.dom.window.navigator, "languages", {configurable: true, value: ["de-DE"]});
    ui.dom.window.dispatchEvent(new ui.dom.window.Event("languagechange"));
    assert.equal(ui.panel.language, "de");
    assert.equal(JSON.stringify(ui.panel.model), model);
    await ui.setIntegrationLanguage("en");
    ui.panel.hass = {...ui.panel._hass, language: "de"};
    ui.dom.window.dispatchEvent(new ui.dom.window.Event("languagechange"));
    assert.equal(ui.panel.language, "en");
    ui.panel.remove();
    ui.panel.languagePreference = "auto";
    ui.dom.window.dispatchEvent(new ui.dom.window.Event("languagechange"));
    assert.equal(ui.panel.language, "en");
  } finally { ui.dom.window.close(); }
});

test("English editor translates confirmation dialogs, counts and dynamic labels safely", async () => {
  const ui = await createPanel({integrationLanguage: "en"});
  try {
    const name = "Wohnzimmer <img src=x> {count}";
    ui.select("new-menu", name);
    ui.button("Add submenu").click();
    assert.equal(ui.root.querySelector('[data-field^="label-"]').hint, "0 entries");
    ui.button("Edit submenu").click();
    assert.equal(ui.root.querySelector(".section-heading p").textContent, `Edit and sort entries in “${name}”.`);
    ui.select("entity", "light.ceiling");
    ui.button("Add entity").click();
    ui.button("Home Assistant").click();
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
    assert.equal(ui.notifications.length, 0);
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
    assert.equal(ui.saved().menus[0].children[0].label, "Wohnzimmer");
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
    assert.equal(ui.notifications.length, 0);
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
    assert.deepEqual(ui.requests, ["enigmaha_companion/v1/configuration"]);
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

test("filter options use HA names in the editor language and retain native values", async () => {
  const requests = [];
  const labels = {
    de: {"component.cover.entity_component._.name": "Abdeckung",
      "component.sensor.entity_component.temperature.name": "Temperatur",
      "component.sensor.entity_component.power.name": "Leistung",
      "component.binary_sensor.entity_component._.name": "Binärsensor",
      "component.sensor.entity_component.battery.name": "Batteriestand",
      "component.binary_sensor.entity_component.battery.name": "Batterie"},
    en: {"component.cover.entity_component._.name": "Cover",
      "component.sensor.entity_component.temperature.name": "Temperature",
      "component.sensor.entity_component.power.name": "Power"},
  };
  const ui = await createPanel({haLanguage: "en", callWS: async request => {
    requests.push(request);
    return {resources: labels[request.language]};
  }});
  try {
    const states = {...ui.panel._hass.states};
    for (const [entity_id, device_class] of [["cover.blind", ""], ["sensor.battery", "battery"],
      ["binary_sensor.battery", "battery"], ["sensor.custom", "custom_class"], ["custom.example", ""]]) {
      states[entity_id] = {entity_id, attributes: {device_class}, state: "0"};
    }
    ui.panel.hass = {...ui.panel._hass, states};
    await tick();
    const options = name => Array.from(ui.root.querySelector(`[data-selector="${name}"]`).selector.select.options);
    const label = (name, value) => options(name).find(option => option.value === value)?.label;
    assert.equal(label("domain", "cover"), "Abdeckung");
    assert.equal(label("domain", "custom"), "custom");
    assert.equal(label("device_class", "temperature"), "Temperatur");
    assert.equal(label("device_class", "power"), "Leistung");
    assert.equal(label("device_class", "custom_class"), "custom_class");
    assert.equal(options("device_class").filter(option => option.value === "battery").length, 1);
    assert.deepEqual(options("device_class").map(option => option.label),
      options("device_class").map(option => option.label).sort((a, b) => a.localeCompare(b, "de")));
    ui.select("domain", "sensor");
    assert.equal(label("device_class", "battery"), "Batteriestand");
    ui.select("device_class", "temperature");
    ui.select("entity", "sensor.temp");
    assert.equal(ui.button("Entität hinzufügen").disabled, false);
    ui.panel.setLanguage("en");
    await tick();
    assert.equal(label("domain", "cover"), "Cover");
    assert.equal(label("device_class", "temperature"), "Temperature");
    assert.equal(ui.root.querySelector('[data-selector="device_class"]').value, "temperature");
    assert.equal(ui.root.querySelector('[data-selector="entity"]').selector.entity.filter.domain, "sensor");
    assert.equal(ui.root.querySelector('[data-selector="entity"]').selector.entity.filter.device_class, "temperature");
    ui.button("Add entity").click();
    assert.equal(ui.panel.model.root.children[0].entity_id, "sensor.temp");
    ui.panel.setLanguage("de");
    ui.select("domain", "binary_sensor");
    assert.equal(label("device_class", "battery"), "Batterie");
    assert.equal(label("device_class", "temperature"), undefined);
    await tick();
    assert.equal(requests.length, 3, "Load only new domains and languages, reusing earlier translations");
    assert.ok(requests.every(request => request.type === "frontend/get_translations"
      && request.category === "entity_component"));
  } finally {ui.dom.window.close();}
});

test("late filter translations preserve controls, selection and unsaved input across language changes", async () => {
  const pending = [];
  const ui = await createPanel({callWS: request => new Promise(resolve => pending.push({request, resolve}))});
  try {
    ui.select("domain", "sensor");
    ui.select("device_class", "temperature");
    ui.select("entity", "sensor.temp");
    ui.select("new-menu", "Unfertiger Entwurf");
    ui.panel.setLanguage("en");
    await tick();
    const picker = ui.root.querySelector('[data-selector="entity"]');
    const classes = ui.root.querySelector('[data-selector="device_class"]');
    const draft = ui.root.querySelector('[data-field="new-menu"]');
    pending.find(item => item.request.language === "en").resolve({resources: {
      "component.sensor.entity_component.temperature.name": "Temperature"}});
    await tick();
    pending.find(item => item.request.language === "de").resolve({resources: {
      "component.sensor.entity_component.temperature.name": "Temperatur"}});
    await tick();
    assert.equal(classes.selector.select.options.find(option => option.value === "temperature").label, "Temperature");
    assert.equal(ui.root.querySelector('[data-selector="entity"]'), picker);
    assert.equal(ui.root.querySelector('[data-selector="device_class"]'), classes);
    assert.equal(picker.value, "sensor.temp");
    assert.equal(classes.value, "temperature");
    assert.equal(ui.root.querySelector('[data-field="new-menu"]'), draft);
    assert.equal(draft.value, "Unfertiger Entwurf");
    assert.equal(ui.panel.dirty, false);
  } finally {ui.dom.window.close();}
});

test("unavailable filter translations keep the native entity picker usable without repeated requests", async () => {
  let requests = 0;
  const ui = await createPanel({haLanguage: "de", callWS: async () => { requests++; throw new Error("offline"); }});
  try {
    ui.panel.hass = {...ui.panel._hass, localize: key =>
      key === "component.sensor.entity_component.temperature.name" ? "Temperatur" : key};
    ui.select("domain", "sensor");
    ui.select("device_class", "temperature");
    ui.select("entity", "sensor.temp");
    await tick();
    assert.equal(ui.button("Entität hinzufügen").disabled, false);
    const options = ui.root.querySelector('[data-selector="device_class"]').selector.select.options;
    assert.equal(options.find(option => option.value === "temperature").label, "Temperatur");
    assert.equal(options.find(option => option.value === "power").label, "power");
    assert.equal(ui.panel.loading, false);
    assert.equal(requests, 1);
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

test("failed HA component loading leaves loading state without notifications", async () => {
  const ui = await createPanel({brokenSelectors: true});
  try {
    assert.equal(ui.panel.loading, false);
    assert.equal(ui.notifications.length, 0);
    assert.equal(ui.root.querySelector('[data-selector="entity"]'), null);
  } finally {ui.dom.window.close();}
});

test("preview and generic save errors preserve the draft without notifications", async () => {
  const ui = await createPanel({overview: true});
  try {
    ui.renameMenu("Entwurf");
    ui.select("preview-user", "anna");
    const draft = JSON.stringify(ui.panel.model);
    ui.panel._hass.callApi = async () => { throw {status: 500}; };
    await ui.panel.preview();
    assert.equal(ui.notifications.length, 0);
    assert.equal(ui.panel.previewBusy, false);
    await ui.panel.save();
    assert.equal(ui.notifications.length, 0);
    assert.equal(JSON.stringify(ui.panel.model), draft);
    assert.equal(ui.panel.dirty, true);
    assert.equal(ui.root.querySelector(".notice, .save-state, .compatibility p"), null);
    const count = ui.notifications.length;
    ui.panel.render();
    assert.equal(ui.notifications.length, count);
  } finally {ui.dom.window.close();}
});


test("native menu title and entry edits preserve display settings without appearance controls", async () => {
  const ui = await createPanel({overview: true});
  try {
    const title = ui.root.querySelector('[data-field="menu-label-home"]');
    ui.select("menu-label-home", "Mein Zuhause");
    assert.equal(ui.root.querySelector('[data-field="menu-label-home"]'), title);
    assert.equal(ui.button("Speichern").disabled, false);
    ui.button("Menüeinträge bearbeiten").click();
    assert.equal(ui.root.querySelector('.receiver-display'), null);
    assert.equal(ui.root.querySelector('[data-selector="font-family"]'), null);
    assert.equal(ui.root.querySelector('[data-selector="font-size"]'), null);
    ui.select("entity", "light.ceiling");
    ui.button("Entität hinzufügen").click();
    const node = ui.panel.model.root.children[0];
    ui.select("label-" + node.id, "Deckenlicht");
    ui.button("Speichern").click();
    await tick();
    assert.equal(ui.saved().menus[0].label, "Mein Zuhause");
    assert.deepEqual(ui.saved().display, {font_family: "Regular", font_size: 28});
    assert.equal(ui.saved().menus[0].children[0].label, "Deckenlicht");
    assert.deepEqual(ui.saved().menus[0].children[0].actions, ["toggle"]);
    assert.equal(ui.button("Speichern").disabled, true);
  } finally {ui.dom.window.close();}
});

test("editor round trips a custom saved font without offering appearance fields", async () => {
  const ui = await createPanel();
  try {
    ui.panel.model.display = {font_family: "MySkinFont", font_size: 31};
    ui.panel.render();
    ui.renameMenu("Mein Zuhause");
    assert.equal(ui.root.querySelector('[data-selector="font-family"]'), null);
    assert.equal(ui.root.querySelector('[data-selector="font-size"]'), null);
    await ui.panel.save();
    assert.deepEqual(ui.saved().display, {font_family: "MySkinFont", font_size: 31});
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
    ui.select("label-" + ui.panel.model.root.children[0].id, "Blocked");
    assert.equal(writes, 1);
    assert.equal(ui.panel.model.root.label, "Home Assistant");
    finish(ui.panel.menuForSave());
    await tick();
    assert.equal(ui.panel.loading, false);
  } finally {ui.dom.window.close();}
});

test("complete menus keep separate trees, duplicate IDs and ACLs safely, and save together", async () => {
  const ui = await createPanel();
  try {
    ui.renameMenu("Wohnung");
    ui.select("entity", "light.ceiling");
    ui.button("Entität hinzufügen").click();
    ui.root.querySelector('[data-access-node="home"]').click();
    ui.select("access-home", "users");
    ui.select("users-home", ["anna"]);
    ui.button("Übernehmen").click();
    await tick();
    const first = ui.panel.model.root;
    ui.button("Zur Menüverwaltung").click();
    ui.button("Menü duplizieren").click();
    const copy = ui.panel.model.root;
    assert.notEqual(copy.id, first.id);
    assert.notEqual(copy.children[0].id, first.children[0].id);
    assert.deepEqual(Array.from(copy.access.users), ["anna"]);
    ui.select("menu-label-" + copy.id, "Privat");
    ui.root.querySelector(`[data-edit-menu="${copy.id}"]`).click();
    ui.root.querySelector(`[data-access-node="${copy.id}"]`).click();
    ui.select("access-" + copy.id, "none");
    ui.button("Übernehmen").click();
    await tick();
    ui.button("Zur Menüverwaltung").click();
    ui.root.querySelector(`[data-edit-menu="${first.id}"]`).click();
    assert.equal(ui.panel.model.root.label, "Wohnung");
    assert.equal(ui.panel.model.root.children.length, 1);
    ui.root.querySelector(`[data-access-node="${first.children[0].id}"]`).click();
    ui.select("access-" + first.children[0].id, "users");
    ui.select("users-" + first.children[0].id, ["ben"]);
    ui.button("Übernehmen").click();
    await tick();
    await ui.panel.save();
    const saved = ui.saved();
    assert.equal(saved.schema_version, 2);
    assert.equal(saved.menus.length, 2);
    assert.equal(saved.menus[1].label, "Privat");
    assert.equal(saved.menus[1].access.mode, "none");
    assert.deepEqual(saved.menus[0].children[0].access, {mode: "users", users: ["ben"]});
    assert.equal(ui.panel.model.root.id, first.id);
  } finally {ui.dom.window.close();}
});

test("user labels omit IDs while missing assignments survive editing and language changes", async () => {
  const ui = await createPanel({overview: true});
  try {
    assert.deepEqual(Array.from(ui.root.querySelector('[data-selector="preview-user"]').selector.select.options,
      option => option.label), ["Anna", "Ben"]);
    ui.root.querySelector('[data-edit-menu="home"]').click();
    ui.root.querySelector('[data-access-node="home"]').click();
    ui.select("access-home", "users");
    ui.button("Übernehmen").click();
    await tick();
    assert.deepEqual(Array.from(ui.panel.model.root.access.users), []);
    ui.panel.model.root.access.users.push("missing-user");
    ui.panel.render();
    ui.root.querySelector('[data-access-node="home"]').click();
    const selector = ui.root.querySelector('[data-selector="users-home"]');
    assert.deepEqual(Array.from(selector.selector.select.options.slice(0, 2), option => option.label), ["Anna", "Ben"]);
    assert.match(selector.selector.select.options.at(-1).label, /Fehlender oder inaktiver Benutzer/);
    assert.doesNotMatch(selector.selector.select.options.at(-1).label, /missing-user/);
    ui.button("Abbrechen").click();
    await tick();
    ui.panel.setLanguage("en");
    ui.root.querySelector('[data-access-node="home"]').click();
    assert.match(ui.root.querySelector('[data-selector="users-home"]').selector.select.options.at(-1).label,
      /Missing or inactive user/);
    ui.button("Apply").click();
    await tick();
    await ui.panel.save();
    assert.deepEqual(ui.saved().menus[0].access.users, ["missing-user"]);
    ui.root.querySelector('[data-access-node="home"]').click();
    ui.select("users-home", []);
    ui.button("Apply").click();
    await tick();
    await ui.panel.save();
    assert.deepEqual(ui.saved().menus[0].access, {mode: "users", users: []});
  } finally {ui.dom.window.close();}
});

test("unsaved changes, successful saves and failures do not emit notifications", async () => {
  const ui = await createPanel();
  try {
    assert.equal(ui.root.querySelector(".save-state, .notice"), null);
    assert.doesNotMatch(ui.root.textContent, /Alle Änderungen gespeichert/);
    ui.renameMenu("Wohnung");
    assert.equal(ui.notifications.length, 0);
    const count = ui.notifications.length;
    ui.renameMenu("Wohnung 2");
    assert.equal(ui.notifications.length, count);
    await ui.panel.save();
    assert.equal(ui.notifications.length, 0);
    assert.equal(ui.panel.dirty, false);
    assert.equal(ui.button("Speichern").disabled, true);
    assert.equal(ui.root.querySelector(".save-state, .notice"), null);
    ui.button("Zur Menüverwaltung").click();
    ui.panel.users.push({id: "private-user-id", name: ""});
    ui.panel.render();
    const options = ui.root.querySelector('[data-selector="preview-user"]').selector.select.options;
    assert.equal(options.at(-1).label, "Benutzer ohne Namen");
    ui.button("Menüeinträge bearbeiten").click();
    ui.fail();
    ui.renameMenu("Privat");
    await ui.panel.save();
    assert.equal(ui.notifications.length, 0);
    const failedCount = ui.notifications.length;
    await ui.panel.save();
    assert.equal(ui.notifications.length, failedCount);
    assert.equal(ui.root.querySelector(".notice"), null);
    assert.equal(ui.panel.dirty, true);
  } finally {ui.dom.window.close();}
});

test("user dialog isolates drafts, cancels safely, and applies only changed rules", async () => {
  const ui = await createPanel();
  try {
    const root = ui.panel.model.root;
    const trigger = ui.root.querySelector('[data-access-node="home"]');
    assert.equal(ui.root.querySelector('[data-selector="access-home"]'), null);
    trigger.focus(); trigger.click();
    const dialog = ui.root.querySelector("dialog");
    const mode = dialog.querySelector('[data-selector="access-home"]');
    assert.equal(ui.button("Übernehmen").getAttribute("variant"), null);
    ui.select("access-home", "users");
    ui.select("users-home", ["anna", "ben", "anna"]);
    assert.equal(dialog.querySelector('[data-selector="access-home"]'), mode, "Changing mode preserves the focused selector");
    assert.equal(root.access.mode, "all");
    assert.equal(ui.panel.dirty, false);
    ui.button("Speichern").click();
    ui.button("Zur Menüverwaltung").click();
    assert.equal(ui.panel.view, "entries");
    assert.equal(ui.saved(), undefined);
    assert.equal(ui.panel.configuration.menus.length, 1);
    ui.panel.render();
    assert.equal(ui.root.querySelector("dialog"), dialog);
    ui.button("Abbrechen").click();
    await tick();
    assert.equal(root.access.mode, "all");
    assert.equal(ui.panel.dirty, false);
    ui.root.querySelector('[data-access-node="home"]').click();
    ui.select("access-home", "none");
    ui.root.querySelector("dialog").dispatchEvent(new ui.dom.window.Event("cancel", {cancelable: true}));
    await tick();
    assert.equal(root.access.mode, "all");
    ui.root.querySelector('[data-access-node="home"]').click();
    ui.button("Übernehmen").click();
    await tick();
    assert.equal(ui.panel.dirty, false, "Unchanged access does not dirty the editor");
    ui.root.querySelector('[data-access-node="home"]').click();
    ui.select("access-home", "users");
    ui.select("users-home", ["anna", "ben", "anna"]);
    ui.select("access-home", "none");
    ui.select("access-home", "users");
    assert.deepEqual(Array.from(ui.root.querySelector('[data-selector="users-home"]').value), ["anna", "ben"]);
    ui.button("Übernehmen").click();
    await tick();
    assert.deepEqual(JSON.parse(JSON.stringify(root.access)), {mode: "users", users: ["anna", "ben"]});
    assert.equal(ui.panel.dirty, true);
    assert.equal(ui.saved(), undefined, "Applying a dialog only updates the draft");
    ui.root.querySelector('[data-access-node="home"]').click();
    ui.select("access-home", "none");
    ui.panel.remove();
    await tick();
    assert.equal(root.access.mode, "users");
    assert.equal(ui.panel.confirmation, undefined);
  } finally {ui.dom.window.close();}
});

test("account-edit precedes deletion on entity and submenu rows and both submenu paths edit the same rule", async () => {
  const ui = await createPanel();
  try {
    ui.select("entity", "light.ceiling");
    ui.button("Entität hinzufügen").click();
    ui.select("new-menu", "Wohnzimmer <img>");
    ui.button("Untermenü hinzufügen").click();
    for (const row of ui.root.querySelectorAll(".row")) {
      const buttons = row.querySelector(".entry-actions").children;
      assert.equal(buttons[buttons.length - 2].firstElementChild.icon, "mdi:account-edit");
      assert.equal(buttons[buttons.length - 1].firstElementChild.icon, "mdi:delete-outline");
      assert.equal(row.querySelector("ha-selector, details"), null);
    }
    const submenu = ui.panel.model.root.children.find(node => node.type === "menu");
    ui.root.querySelector(`[data-access-node="${submenu.id}"]`).click();
    assert.match(ui.root.querySelector("dialog").textContent, /Wohnzimmer <img>/);
    assert.equal(ui.root.querySelector("dialog img"), null);
    assert.deepEqual(Array.from(ui.root.querySelector(`[data-selector="access-${submenu.id}"]`).selector.select.options, option => option.value),
      ["inherit", "users", "none"]);
    ui.select("access-" + submenu.id, "users");
    ui.select("users-" + submenu.id, ["ben"]);
    ui.button("Übernehmen").click();
    await tick();
    ui.button("Untermenü bearbeiten").click();
    ui.root.querySelector(`[data-access-node="${submenu.id}"]`).click();
    assert.deepEqual(Array.from(ui.root.querySelector(`[data-selector="users-${submenu.id}"]`).value), ["ben"]);
    ui.button("Abbrechen").click();
    await tick();
    assert.equal(submenu.access.mode, "users");
  } finally {ui.dom.window.close();}
});

test("last complete menu can be removed after confirmation and recreated without reloading", async () => {
  const ui = await createPanel({overview: true});
  try {
    ui.button("Menü entfernen").click();
    assert.equal(ui.panel.configuration.menus.length, 1);
    ui.root.querySelector("dialog .dialog-actions").lastElementChild.click();
    await tick();
    assert.equal(ui.panel.configuration.menus.length, 0);
    assert.match(ui.root.textContent, /Keine Menüs vorhanden/);
    await ui.panel.save();
    assert.deepEqual(ui.saved().menus, []);
    ui.button("Menü anlegen").click();
    assert.equal(ui.panel.configuration.menus.length, 1);
    assert.equal(ui.panel.model.root.access.mode, "all");
    assert.equal(ui.panel.dirty, true);
  } finally {ui.dom.window.close();}
});

test("preview submits the unsaved collection, escapes labels and does not save", async () => {
  const ui = await createPanel();
  try {
    // Native HA buttons expose their internal focus target after Lit renders.
    const prototype = ui.dom.window.customElements.get("ha-button").prototype;
    Object.defineProperty(prototype, "updateComplete", {get() {
      return Promise.resolve().then(() => { this.focusReady = true; });
    }});
    prototype.focus = function() { assert.equal(this.focusReady, true); };
    ui.renameMenu("Entwurf");
    ui.button("Zur Menüverwaltung").click();
    ui.select("preview-user", "anna");
    let sent;
    ui.panel._hass.callApi = async (method, route, body) => {
      assert.equal(method, "POST");
      assert.equal(route, "enigmaha_companion/v1/preview");
      sent = body;
      return {root: {type: "menu", id: "home", label: "<img src=x>", children: []}};
    };
    ui.button("Vorschau öffnen").click();
    await tick();
    assert.equal(sent.user_id, "anna");
    assert.equal(sent.configuration.menus[0].label, "Entwurf");
    assert.equal(ui.root.querySelector("dialog img"), null);
    assert.match(ui.root.querySelector("dialog").textContent, /<img src=x>/);
    assert.equal(ui.root.querySelector("dialog").querySelectorAll("ha-button").length, 1);
    assert.equal(ui.root.querySelector(".notice"), null);
    assert.equal(ui.panel.previewBusy, true);
    ui.button("Schließen").click();
    await tick();
    assert.equal(ui.root.querySelector("dialog"), null);
    assert.equal(ui.panel.dirty, true);
    assert.equal(ui.saved(), undefined);
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
    assert.deepEqual(buttons.map(b => b.label), ["Untermenü bearbeiten", "Nach oben", "Nach unten", "Benutzereinstellungen", "Entfernen"]);
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
    assert.deepEqual(sent.menus[0].children[0].children.map(n => n.actions),
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
    assert.deepEqual(ui.saved().menus[0].children.map(n => n.id), ["room", "light", "power"]);
    assert.equal(ui.saved().menus[0].children[0].children[0].entity_id, "sensor.temp");
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

test("menu overview opens first and separates sorting, access and preview from entry editing", async () => {
  const ui = await createPanel({overview: true});
  try {
    assert.equal(ui.panel.view, "menus");
    assert.equal(ui.root.querySelector('.menu-column h2').textContent, "Menüs verwalten");
    assert.equal(ui.root.querySelector('.tools-column h2').textContent, "Vorschau");
    assert.equal(ui.root.querySelector('[data-selector="entity"]'), null);
    const first = ui.panel.model.root;
    ui.select("menu-label-home", "Gemeinsam <img>");
    ui.button("Menü anlegen").click();
    const second = ui.panel.model.root;
    ui.select("menu-label-" + second.id, "Privat");
    assert.equal(ui.panel.view, "menus");
    for (const row of ui.root.querySelectorAll('.row')) {
      const actions = [...row.querySelectorAll('.entry-actions ha-icon-button')];
      assert.deepEqual(actions.map(button => button.firstElementChild.icon),
        ["mdi:pencil", "mdi:content-copy", "mdi:arrow-up", "mdi:arrow-down", "mdi:delete-outline"]);
    }
    assert.equal(ui.root.querySelector('[data-access-node]'), null);
    let rows = ui.root.querySelectorAll('.row');
    assert.equal(rows[0].querySelectorAll('ha-icon-button')[2].disabled, true);
    assert.equal(rows[1].querySelectorAll('ha-icon-button')[3].disabled, true);
    ui.root.querySelector(`[data-edit-menu="${first.id}"]`).click();
    assert.equal(ui.panel.view, "entries");
    assert.equal(ui.root.querySelector('[data-selector="preview-user"]'), null);
    assert.doesNotMatch(ui.root.textContent, /Menüs verwalten/);
    ui.select("new-menu", "Raum");
    ui.button("Untermenü hinzufügen").click();
    ui.button("Untermenü bearbeiten").click();
    const room = ui.panel.path.at(-1);
    ui.select("entity", "sensor.temp");
    ui.button("Entität hinzufügen").click();
    ui.select("new-menu", "Noch im Entwurf");
    ui.button("Zur Menüverwaltung").click();
    assert.equal(ui.panel.configuration.menus[0].children[0].children[0].entity_id, "sensor.temp");
    ui.root.querySelector(`[data-edit-menu="${first.id}"]`).click();
    assert.equal(ui.panel.path.at(-1), room);
    assert.equal(ui.root.querySelector('[data-field="new-menu"]').value, "Noch im Entwurf");
    ui.button("Zur Menüverwaltung").click();
    ui.root.querySelector(`[data-edit-menu="${second.id}"]`).click();
    ui.root.querySelector(`[data-access-node="${second.id}"]`).click();
    ui.select("access-" + second.id, "users");
    ui.select("users-" + second.id, ["ben"]);
    ui.button("Übernehmen").click();
    await tick();
    ui.button("Zur Menüverwaltung").click();
    ui.root.querySelector(`[data-edit-menu="${first.id}"]`).click();
    ui.button("Zur Menüverwaltung").click();
    ui.root.querySelectorAll('.row')[1].querySelectorAll('ha-icon-button')[2].click();
    await tick();
    assert.deepEqual(Array.from(ui.panel.configuration.menus, node => node.id), [second.id, first.id]);
    assert.equal(ui.panel.model.root, first, "Reordering does not change the open editor's menu");
    assert.equal(ui.scrolled.at(-1).row.dataset.nodeId, second.id);
    const sortable = ui.root.querySelector('ha-sortable');
    assert.equal(sortable.rollback, true);
    sortable.dispatchEvent(new ui.dom.window.CustomEvent("item-moved", {detail: {oldIndex: 0, newIndex: 1}}));
    assert.equal(ui.panel.configuration.menus[0], second, "Wait for native HA rollback");
    sortable.dispatchEvent(new ui.dom.window.CustomEvent("drag-end"));
    await tick();
    assert.deepEqual(Array.from(ui.panel.configuration.menus, node => node.id), [first.id, second.id]);
    await ui.panel.save();
    assert.equal(ui.panel.view, "menus");
    assert.equal(ui.saved().menus[0].label, "Gemeinsam <img>");
    assert.deepEqual(ui.saved().menus[1].access, {mode: "users", users: ["ben"]});
    assert.equal(ui.saved().menus[0].children[0].children[0].entity_id, "sensor.temp");
    assert.equal(ui.root.querySelector('img'), null);
    ui.panel.setLanguage("en");
    assert.equal(ui.root.querySelector('.menu-column h2').textContent, "Manage menus");
    ui.button("Edit menu entries").click();
    assert.ok(ui.button("Back to menu management"));
  } finally {ui.dom.window.close();}
});

test("menu overview rejects invalid and stale drags and preserves rows when deletion is cancelled", async () => {
  const ui = await createPanel({overview: true});
  try {
    ui.button("Menü anlegen").click();
    const menus = ui.panel.configuration.menus;
    const ids = Array.from(menus, node => node.id);
    ui.panel.dirty = false;
    ui.panel.render();
    const drag = detail => {
      const sortable = ui.root.querySelector('ha-sortable');
      sortable.dispatchEvent(new ui.dom.window.CustomEvent("item-moved", {detail}));
      sortable.dispatchEvent(new ui.dom.window.CustomEvent("drag-end"));
    };
    for (const detail of [{oldIndex: -1, newIndex: 0}, {oldIndex: 0, newIndex: 2},
      {oldIndex: 0.5, newIndex: 1}, {oldIndex: 0, newIndex: 0}]) {
      drag(detail);
      await tick();
    }
    assert.equal(ui.panel.dirty, false);
    drag({oldIndex: 0, newIndex: 1});
    ui.button("Menüeinträge bearbeiten").click();
    await tick();
    assert.deepEqual(Array.from(menus, node => node.id), ids);
    ui.button("Zur Menüverwaltung").click();
    ui.button("Menü entfernen").click();
    drag({oldIndex: 0, newIndex: 1});
    await tick();
    assert.deepEqual(Array.from(menus, node => node.id), ids);
    ui.button("Abbrechen").click();
    await tick();
    assert.equal(ui.panel.dirty, false);
    ui.panel.loading = true;
    ui.panel.render();
    assert.equal(ui.root.querySelector('ha-sortable').disabled, true);
    drag({oldIndex: 0, newIndex: 1});
    await tick();
    assert.deepEqual(Array.from(menus, node => node.id), ids);
    assert.equal(ui.panel.dirty, false);
  } finally {ui.dom.window.close();}
});
