/* EnigmaHA Companion: native HA custom panel, no external assets. */
class EnigmaHAPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this.path = [];
    this.dirty = false;
    this.loading = false;
    this.message = "";
    this.entityFilters = {domain: "", area: "", device_class: ""};
    this.selectedEntity = undefined;
    this.selectorsReady = false;
    this.filtersOpen = false;
    this.menuDraft = "";
  }

  set hass(value) {
    this._hass = value;
    if (!this.model && !this.loading) this.load();
    const menuButton = this.shadowRoot.querySelector("ha-menu-button");
    if (menuButton) menuButton.hass = value;
    for (const selector of this.shadowRoot.querySelectorAll("ha-selector")) selector.hass = value;
    this.updateEntryEntities();
    this.updateEntitySelector();
  }

  el(tag, text, attrs = {}) {
    const node = document.createElement(tag);
    if (text !== null) node.textContent = text;
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    return node;
  }

  button(text, action, disabled = false, appearance = "plain") {
    const button = this.el("ha-button", text, {appearance});
    button.disabled = disabled || this.loading;
    button.onclick = () => { if (!button.disabled && !this.confirmation) action(); };
    return button;
  }

  icon(name) {
    const icon = this.el("ha-icon", null, {"aria-hidden": "true"});
    icon.icon = "mdi:" + name;
    return icon;
  }

  entityDescription(entityId) {
    const name = this._hass.states?.[entityId]?.attributes.friendly_name;
    return name ? `${name} (${entityId})` : `(${entityId})`;
  }

  updateEntryEntities() {
    for (const icon of this.shadowRoot.querySelectorAll("ha-state-icon[data-entity-id]")) {
      const entityId = icon.dataset.entityId;
      const state = this._hass.states?.[entityId];
      icon.hass = this._hass;
      icon.stateObj = state || {entity_id: entityId, state: "unknown", attributes: {}};
      icon.icon = this._hass.entities?.[entityId]?.icon || state?.attributes.icon;
    }
    for (const field of this.shadowRoot.querySelectorAll("ha-input[data-entity-id]")) {
      field.hint = this.entityDescription(field.dataset.entityId);
    }
  }

  entityActions(entityId) {
    return ["light", "switch", "input_boolean"].includes(entityId.split(".")[0]) ? ["toggle"] : [];
  }

  menuForSave() {
    // Actions remain part of the receiver protocol, but are derived from the
    // supported entity domains instead of being an editor preference.
    const prepare = node => node.type === "menu"
      ? {...node, children: node.children.map(prepare)}
      : {...node, actions: this.entityActions(node.entity_id)};
    return {...this.model, root: prepare(this.model.root)};
  }

  iconButton(label, icon, action, disabled = false) {
    const button = this.el("ha-icon-button", null);
    button.label = label;
    button.disabled = disabled || this.loading;
    button.append(this.icon(icon));
    button.onclick = () => { if (!button.disabled && !this.confirmation) action(); };
    return button;
  }

  confirmAction(title, text, confirmText) {
    if (this.confirmation) return Promise.resolve(false);
    // A modal HTML dialog supplies focus trapping, Escape and a top-layer
    // backdrop. Its surface uses HA theme tokens and native HA action buttons.
    // This also works before HA's lazily loaded dialog bundles are registered.
    const dialog = this.el("dialog", null, {class: "confirmation-dialog", "aria-labelledby": "confirmation-title",
      "aria-describedby": "confirmation-text"});
    const previousFocus = this.shadowRoot.activeElement;
    let resolve;
    const result = new Promise(done => { resolve = done; });
    const finish = accepted => {
      if (this.confirmation?.element !== dialog) return;
      this.confirmation = undefined;
      if (dialog.open) dialog.close();
      dialog.remove();
      if (previousFocus?.isConnected) previousFocus.focus();
      resolve(accepted);
    };
    const cancel = this.button("Abbrechen", () => finish(false));
    const confirm = this.button(confirmText, () => finish(true), false, "filled");
    // Dialog actions remain usable while background editor actions are blocked.
    cancel.onclick = () => finish(false);
    confirm.onclick = () => finish(true);
    cancel.setAttribute("autofocus", "");
    confirm.setAttribute("variant", "danger");
    const actions = this.el("div", null, {class: "dialog-actions"});
    actions.append(cancel, confirm);
    dialog.append(this.el("h2", title, {id: "confirmation-title"}),
      this.el("p", text, {id: "confirmation-text"}), actions);
    dialog.addEventListener("cancel", event => { event.preventDefault(); finish(false); });
    dialog.addEventListener("close", () => finish(false));
    this.confirmation = {element: dialog, cancel: () => finish(false)};
    this.shadowRoot.append(dialog);
    dialog.showModal();
    Promise.resolve(cancel.updateComplete).then(() => {
      if (dialog.open) cancel.focus();
    });
    return result;
  }

  disconnectedCallback() {
    this.confirmation?.cancel();
    this.stopDragScroll?.();
  }

  startDragScroll(sortable, menuColumn) {
    this.stopDragScroll?.();
    const listeners = new AbortController();
    const narrowLayout = window.matchMedia("(max-width:900px)");
    let pointer, frame, previousTime;
    const stop = () => {
      listeners.abort();
      window.cancelAnimationFrame(frame);
      if (this.stopDragScroll === stop) this.stopDragScroll = undefined;
    };
    this.stopDragScroll = stop;
    const track = event => { pointer = event.touches?.[0] || event; };
    for (const name of ["dragover", "pointermove", "mousemove", "touchmove"]) {
      document.addEventListener(name, track, {capture: true, passive: true, signal: listeners.signal});
    }
    for (const name of ["drop", "dragend", "pointerup", "pointercancel", "touchend", "touchcancel"]) {
      document.addEventListener(name, stop, {capture: true, signal: listeners.signal});
    }
    window.addEventListener("blur", stop, {signal: listeners.signal});
    document.addEventListener("keydown", event => { if (event.key === "Escape") stop(); }, {signal: listeners.signal});
    const scroll = time => {
      if (!sortable.isConnected || this.loading || this.confirmation) { stop(); return; }
      const elapsed = Math.min(32, previousTime === undefined ? 16 : time - previousTime);
      previousTime = time;
      if (pointer) {
        const mobile = narrowLayout.matches;
        const container = mobile ? this : menuColumn;
        const bounds = container.getBoundingClientRect();
        const list = sortable.getBoundingClientRect();
        // In the single-column layout keep the sticky header and the settings
        // below the list out of the drag area.
        const top = mobile ? Math.max(list.top, this.shadowRoot.querySelector("header").getBoundingClientRect().bottom) : bounds.top;
        const bottom = mobile ? Math.min(list.bottom, bounds.bottom) : bounds.bottom;
        const zone = Math.min(64, (bottom - top) / 3);
        if (zone > 0 && pointer.clientX >= bounds.left && pointer.clientX <= bounds.right
          && pointer.clientY >= top - 24 && pointer.clientY <= bottom + 24) {
          const direction = pointer.clientY < top + zone ? -Math.min(1, (top + zone - pointer.clientY) / zone)
            : pointer.clientY > bottom - zone ? Math.min(1, (pointer.clientY - bottom + zone) / zone) : 0;
          const limit = container.scrollHeight - container.clientHeight;
          container.scrollTop = Math.max(0, Math.min(limit, container.scrollTop + direction * elapsed * .6));
        }
      }
      frame = window.requestAnimationFrame(scroll);
    };
    frame = window.requestAnimationFrame(scroll);
  }

  markDirty() {
    this.dirty = true;
    const status = this.shadowRoot.querySelector(".save-state");
    if (status) status.textContent = "Ungespeicherte Änderungen";
    const save = this.shadowRoot.querySelector('[data-action="save"]');
    if (save) save.disabled = this.loading;
    const notice = this.shadowRoot.querySelector(".notice");
    if (notice) notice.textContent = "";
    this.message = "";
  }

  async revealEntry(id) {
    const row = [...this.shadowRoot.querySelectorAll(".row")].find(row => row.dataset.nodeId === id);
    if (!row) return;
    // Let HA finish its fields and the browser calculate the new list height.
    await Promise.all([...row.querySelectorAll("ha-input")].map(field => field.updateComplete));
    await new Promise(resolve => window.requestAnimationFrame(resolve));
    if (!row.isConnected) return;
    row.classList.add("revealed");
    row.scrollIntoView({block: "center", inline: "nearest",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"});
  }

  moveEntry(menu, oldIndex, newIndex) {
    if (this.loading || this.confirmation || menu !== this.path.at(-1) || !Number.isInteger(oldIndex)
      || !Number.isInteger(newIndex) || oldIndex < 0 || newIndex < 0
      || oldIndex >= menu.children.length || newIndex >= menu.children.length || oldIndex === newIndex) return;
    const [node] = menu.children.splice(oldIndex, 1);
    menu.children.splice(newIndex, 0, node);
    this.markDirty();
    this.render();
    this.revealEntry(node.id);
  }

  textField(name, title, value, change, options = {}) {
    const input = this.el("ha-input", null, {"data-field": name});
    input.label = title;
    input.value = String(value ?? "");
    input.type = options.type || "text";
    input.required = options.required ?? true;
    input.disabled = this.loading || !this.selectorsReady;
    if (input.type === "number") {
      input.min = options.min;
      input.max = options.max;
      input.step = options.step;
      input.inputmode = "numeric";
      input.autoValidate = true;
    }
    input.addEventListener("input", event => {
      event.stopPropagation();
      if (!input.disabled) change(input.value);
    });
    return input;
  }

  field(parent, name, title, value, change, options) {
    const input = this.textField(name, title, value, value => {
      change(value);
      this.markDirty();
    }, options);
    parent.append(input);
    return input;
  }

  selectionField(parent, name, title, value, options, change) {
    let selected = String(value);
    const field = this.selector(name, title, {select: {mode: "dropdown", options}}, selected, value => {
      // A required dropdown must not clear the stored value or accept free text.
      if (!options.some(option => option.value === value)) {
        field.value = selected;
        return;
      }
      selected = value;
      change(value);
      this.markDirty();
    });
    field.required = true;
    parent.append(field);
    return field;
  }

  card(title, description) {
    const card = this.el("ha-card", null);
    const heading = this.el("div", null, {class: "section-heading"});
    heading.append(this.el("h2", title));
    if (description) heading.append(this.el("p", description));
    card.append(heading);
    return card;
  }

  async load() {
    if (this.loading || this.confirmation) return;
    if (this.dirty && !await this.confirmAction("Ungespeicherte Änderungen verwerfen?",
      "Beim erneuten Laden gehen deine ungespeicherten Änderungen verloren.", "Verwerfen und neu laden")) return;
    if (!this.isConnected) return;
    this.loading = true;
    this.message = "Menü wird geladen …";
    this.render();
    try {
      const [model] = await Promise.all([
        this._hass.callApi("GET", "enigmaha_companion/v1/config"),
        this.ensureSelectors(),
      ]);
      this.model = model;
      this.selectedEntity = undefined;
      this.path = [model.root];
      this.dirty = false;
      this.message = "";
    } catch (_) {
      this.message = "Editor konnte nicht geladen werden. HA-Seite neu laden und Administrator-Anmeldung prüfen.";
    } finally { this.loading = false; this.render(); }
  }

  async save() {
    if (this.loading || this.confirmation) return;
    this.loading = true;
    this.render();
    try {
      const ids = this.path.map(node => node.id);
      this.model = await this._hass.callApi("PUT", "enigmaha_companion/v1/config", this.menuForSave());
      this.path = [this.model.root];
      for (const id of ids.slice(1)) {
        const child = this.path[this.path.length - 1].children.find(n => n.id === id);
        if (!child) break;
        this.path.push(child);
      }
      this.dirty = false;
      this.message = "Gespeichert. Das Receiver-Menü wird beim nächsten Laden aktualisiert.";
    } catch (error) {
      this.message = Number(error.status_code || error.status) === 409
        ? "Das Menü wurde inzwischen geändert. Neu laden und Änderungen erneut vornehmen."
        : "Speichern fehlgeschlagen. Namen, Schriftgröße und Menüstruktur prüfen; Änderungen bleiben hier erhalten.";
    } finally { this.loading = false; this.render(); }
  }

  id() {
    // Works on HTTP HA origins as well as secure contexts.
    const values = new Uint32Array(4);
    crypto.getRandomValues(values);
    return "n-" + Array.from(values, n => n.toString(16).padStart(8, "0")).join("");
  }

  async ensureSelectors() {
    // Custom panels can be opened before any HA form has loaded. Load HA's own
    // form/selector and sorting bundles through its card helpers; do not rely
    // on hashed URLs.
    const ready = () => ["ha-selector", "ha-sortable", "ha-input"].every(name => customElements.get(name));
    if (!ready()) {
      const helpers = await window.loadCardHelpers();
      const card = helpers.createCardElement({type: "entities", entities: []});
      await card.constructor.getConfigElement();
    }
    if (!ready()) {
      throw new Error("HA editor components unavailable");
    }
    this.selectorsReady = true;
  }

  selector(name, label, definition, value, changed) {
    const element = this.el("ha-selector", null, {"data-selector": name});
    element.hass = this._hass;
    element.label = label;
    element.selector = definition;
    element.value = value ?? undefined;
    element.required = false;
    element.disabled = this.loading || !this.selectorsReady;
    element.addEventListener("value-changed", event => {
      event.stopPropagation();
      if (this.loading) return;
      element.value = event.detail?.value;
      changed(event.detail?.value);
    });
    return element;
  }

  areaOf(entityId) {
    const entity = this._hass.entities?.[entityId];
    return entity?.area_id || this._hass.devices?.[entity?.device_id]?.area_id;
  }

  matchesFilters(entityId) {
    const state = this._hass.states?.[entityId];
    if (!state) return false;
    const filter = this.entityFilters;
    return (!filter.domain || entityId.split(".")[0] === filter.domain)
      && (!filter.device_class || state.attributes.device_class === filter.device_class)
      && (!filter.area || this.areaOf(entityId) === filter.area);
  }

  entityDefinition() {
    const filter = {};
    for (const key of ["domain", "device_class"]) {
      if (this.entityFilters[key]) filter[key] = this.entityFilters[key];
    }
    const entity = {multiple: false};
    if (Object.keys(filter).length) entity.filter = filter;
    // The entity selector has no area filter field. Resolve HA's entity/device
    // area inheritance and pass the resulting allow-list to the native selector.
    if (this.entityFilters.area) {
      entity.include_entities = Object.keys(this._hass.states || {})
        .filter(id => this.areaOf(id) === this.entityFilters.area);
    }
    return {entity};
  }

  updateEntitySelector() {
    const selector = this.shadowRoot.querySelector('[data-selector="entity"]');
    if (!selector) return;
    if (this.selectedEntity && !this.matchesFilters(this.selectedEntity)) this.selectedEntity = undefined;
    selector.selector = this.entityDefinition();
    selector.value = this.selectedEntity;
    const add = this.shadowRoot.querySelector('[data-action="add-entity"]');
    if (add) add.disabled = this.loading || !this.selectorsReady || !this.selectedEntity || this.path.length >= 9;
  }

  setFilter(name, value) {
    this.entityFilters[name] = typeof value === "string" ? value : "";
    this.selectedEntity = undefined;
    if (name === "domain") this.entityFilters.device_class = "";
    this.render();
  }

  renderEntitySelection(section, current) {
    const details = this.el("details", null, {class: "filter-details"});
    details.open = this.filtersOpen;
    details.ontoggle = () => { if (details.isConnected) this.filtersOpen = details.open; };
    const active = Object.values(this.entityFilters).filter(Boolean).length;
    details.append(this.el("summary", active ? `Auswahl filtern (${active} aktiv)` : "Auswahl filtern"));
    const filters = this.el("div", null, {class: "filters"});
    const states = Object.values(this._hass.states || {});
    const domains = [...new Set(states.map(state => state.entity_id.split(".")[0]))].sort();
    const domainNames = {light: "Licht", switch: "Schalter", input_boolean: "Helfer-Schalter", sensor: "Sensor", binary_sensor: "Binärsensor"};
    filters.append(this.selector("domain", "Entitätstyp", {select: {mode: "dropdown", options:
      domains.map(domain => ({value: domain, label: domainNames[domain] || domain}))}},
      this.entityFilters.domain, value => this.setFilter("domain", value)));
    filters.append(this.selector("area", "Bereich", {area: {}}, this.entityFilters.area,
      value => this.setFilter("area", value)));
    const classes = [...new Set(states.filter(state => !this.entityFilters.domain
      || state.entity_id.split(".")[0] === this.entityFilters.domain)
      .map(state => state.attributes.device_class).filter(Boolean))].sort();
    filters.append(this.selector("device_class", "Geräteklasse", {select: {mode: "dropdown", options: classes}},
      this.entityFilters.device_class, value => this.setFilter("device_class", value)));
    details.append(filters, this.button("Filter zurücksetzen", () => {
      this.entityFilters = {domain: "", area: "", device_class: ""};
      this.selectedEntity = undefined;
      this.render();
    }));
    section.append(details);
    const add = this.el("div", null, {class: "entity-add"});
    const picker = this.selector("entity", "Entität auswählen", this.entityDefinition(), this.selectedEntity, value => {
      this.selectedEntity = typeof value === "string" && this.matchesFilters(value) ? value : undefined;
      this.updateEntitySelector();
    });
    picker.helper = "Nach Name oder Entity-ID suchen. Die Filter oben grenzen die Auswahl ein.";
    const button = this.button("Entität hinzufügen", () => {
      if (!this.selectedEntity || !this.matchesFilters(this.selectedEntity)) return;
      const entityId = this.selectedEntity;
      const state = this._hass.states[entityId];
      const label = String(state.attributes.friendly_name || entityId).slice(0, 120);
      const node = {type: "entity", id: this.id(), label, entity_id: entityId,
        actions: this.entityActions(entityId)};
      current.children.push(node);
      this.selectedEntity = undefined;
      this.markDirty();
      this.render();
      this.revealEntry(node.id);
    }, !this.selectedEntity || !this.selectorsReady || this.path.length >= 9, "filled");
    button.dataset.action = "add-entity";
    add.append(picker, button);
    section.append(add);
  }

  render() {
    const root = this.shadowRoot;
    this.stopDragScroll?.();
    const previousMenu = root.querySelector(".menu-column");
    const menuScroll = previousMenu?.scrollTop || 0;
    const toolsScroll = root.querySelector(".tools-column")?.scrollTop || 0;
    // Preserve an open modal if an editor refresh happens while it is visible.
    for (const child of [...root.childNodes]) {
      if (child !== this.confirmation?.element) child.remove();
    }
    root.append(this.el("style", `
      /* HA's custom-panel wrapper can have automatic height. A percentage alone
         then grows with the list, so sticky descendants never stay in view. */
      :host{display:flex;flex-direction:column;height:100dvh;max-height:100%;min-height:0;overflow:hidden;box-sizing:border-box;color:var(--primary-text-color);background:var(--primary-background-color);font-family:var(--ha-font-family-body,Roboto,Arial,sans-serif);font-size:14px;line-height:1.5}
      *,*::before,*::after{box-sizing:border-box}
      header{position:sticky;top:0;z-index:2;display:flex;flex-shrink:0;align-items:center;gap:16px;min-height:var(--header-height,64px);padding:0 16px 0 4px;background:var(--app-header-background-color);color:var(--app-header-text-color);border-bottom:1px solid var(--divider-color)}
      h1{flex:1;min-width:0;font-size:20px;font-weight:400;line-height:1.3;margin:0}
      .header-actions{display:flex;gap:8px;align-items:center}.header-actions ha-button{--wa-color-on-normal:var(--app-header-text-color)}
      main{display:flex;flex-direction:column;flex:1;min-height:0;width:100%;max-width:1200px;margin:0 auto;padding:24px}
      .intro{display:flex;align-items:start;justify-content:space-between;gap:16px;margin-bottom:20px}
      .intro h2{font-size:24px;font-weight:400;margin:0 0 4px}.intro p{margin:0;color:var(--secondary-text-color)}
      .save-state{font-size:12px;color:var(--secondary-text-color);padding-top:8px;text-align:end}
      .notice{color:var(--secondary-text-color);margin:0 0 20px;overflow-wrap:anywhere}.notice:empty{display:none}
      .intro,.notice{flex-shrink:0}
      .editor-layout{display:grid;flex:1;min-height:0;grid-template-rows:minmax(0,1fr);grid-template-columns:minmax(0,1.65fr) minmax(320px,1fr);gap:24px}
      .column{display:grid;grid-auto-rows:max-content;align-content:start;gap:24px;min-width:0;min-height:0;overflow-y:auto;overscroll-behavior-y:contain;scrollbar-width:thin;scrollbar-gutter:stable}ha-card{min-width:0;overflow:hidden}
      .confirmation-dialog{width:calc(100% - 32px);max-width:450px;max-height:calc(100dvh - 32px);margin:auto;padding:24px;border:0;border-radius:var(--ha-dialog-border-radius,28px);background:var(--ha-dialog-surface-background,var(--card-background-color));color:var(--primary-text-color);font:inherit;box-shadow:var(--dialog-box-shadow,0 8px 32px #0005)}
      .confirmation-dialog::backdrop{background:var(--mdc-dialog-scrim-color,rgba(0,0,0,.6))}
      .confirmation-dialog h2{font-size:var(--ha-font-size-xl,24px);line-height:1.3;font-weight:400;margin:0 0 16px}
      .confirmation-dialog p{color:var(--secondary-text-color);margin:0;overflow-wrap:anywhere}
      .dialog-actions{display:flex;justify-content:end;flex-wrap:wrap;gap:8px;margin-top:24px}
      .section-heading{padding:20px 20px 16px}.section-heading h2{font-size:20px;font-weight:400;line-height:1.4;margin:0}
      .section-heading p{color:var(--secondary-text-color);margin:4px 0 0}
      .card-body{padding:0 20px 20px}.fields{display:grid;gap:12px}
      ha-input{display:block;min-width:0;width:100%;--ha-input-padding-bottom:0;--ha-space-3:8px;--ha-space-5:16px}ha-input::part(wa-base){height:48px}
      .breadcrumbs{display:flex;align-items:center;flex-wrap:wrap;gap:2px;padding:12px 12px 0;color:var(--secondary-text-color);overflow-wrap:anywhere}
      .breadcrumbs ha-button{max-width:100%;--ha-button-height:32px}.breadcrumbs span{padding:4px 8px}
      .breadcrumbs ha-icon{--mdc-icon-size:18px;flex:none}
      ha-sortable{display:block}.entry-list{container-type:inline-size;padding:0;margin:0;list-style:none}.row{display:grid;grid-template-columns:32px 24px minmax(0,1fr) auto;align-items:start;gap:12px;padding:8px 20px;border-top:1px solid var(--divider-color);scroll-margin-block:16px}
      .drag-handle{display:flex;align-items:center;justify-content:center;min-height:40px;margin-top:4px;color:var(--secondary-text-color);cursor:grab;touch-action:none;user-select:none}.drag-handle>*{pointer-events:none}.drag-handle:active{cursor:grabbing}.drag-handle[aria-disabled=true]{opacity:.4;cursor:default;pointer-events:none}
      .row.revealed{animation:entry-reveal 1.6s ease-out}@keyframes entry-reveal{from{box-shadow:inset 4px 0 var(--primary-color);background:rgba(var(--rgb-primary-color),.12)}to{box-shadow:inset 0 0 transparent;background:transparent}}
      @media(prefers-reduced-motion:reduce){.row.revealed{animation:none;box-shadow:inset 3px 0 var(--primary-color)}}
      .row>.entry-icon{margin-top:12px;color:var(--secondary-text-color)}.entry-content{min-width:0;overflow-wrap:anywhere}
      .entry-actions{display:flex;align-items:center;flex-wrap:wrap;justify-content:end;width:max-content;max-width:100%;margin-top:4px;gap:0;--ha-icon-button-size:40px}.entry-actions ha-icon-button{flex:none}
      .danger{color:var(--error-color)}
      @container(max-width:560px){.row{grid-template-columns:32px 24px minmax(0,1fr);gap:4px 12px}.entry-actions{grid-column:3;justify-self:end;margin-top:0}}
      .empty{display:flex;flex-direction:column;align-items:center;gap:8px;text-align:center;padding:36px 24px 44px;color:var(--secondary-text-color);border-top:1px solid var(--divider-color)}
      .empty ha-icon{--mdc-icon-size:40px;margin-bottom:8px}.empty strong{font-size:16px;font-weight:500;color:var(--primary-text-color)}.empty p{margin:0;max-width:320px}
      .filter-details{margin-bottom:20px}summary{cursor:pointer;color:var(--primary-text-color);padding:4px 0;min-height:32px}summary:focus-visible{outline:2px solid var(--primary-color);outline-offset:4px}
      .filters{display:grid;gap:16px;margin:16px 0 8px}ha-selector{display:block;min-width:0;width:100%}
      .entity-add,.menu-add{display:grid;gap:16px}.entity-add ha-button,.menu-add ha-button{justify-self:end}
      .depth-notice{margin:0 0 16px;color:var(--secondary-text-color)}
      @media(max-width:900px){:host{display:block;overflow:auto}main{display:block;min-height:auto}.editor-layout{grid-template-columns:minmax(0,1fr);grid-template-rows:auto}.column{display:contents;overflow:visible;scrollbar-gutter:auto}.row{scroll-margin-block:calc(var(--header-height,64px) + 16px) 16px}.save-state{max-width:150px}}
      @media(max-width:600px){main{padding:16px}.editor-layout,.column{gap:16px}header{gap:4px;padding-inline-end:8px}h1{font-size:18px}.header-actions{gap:0}.intro{display:block}.save-state{text-align:start;max-width:none}.row{padding:8px 16px}.section-heading{padding:16px}.card-body{padding:0 16px 16px}}
    `));
    const header = this.el("header", null);
    const drawer = this.el("ha-menu-button", null);
    drawer.hass = this._hass;
    const actions = this.el("div", null, {class: "header-actions"});
    const reload = this.iconButton("Neu laden", "refresh", () => this.load());
    const save = this.button("Speichern", () => this.save(), !this.model || !this.dirty, "accent");
    save.dataset.action = "save";
    actions.append(reload, save);
    header.append(drawer, this.el("h1", "EnigmaHA Companion"), actions);
    root.append(header);
    const main = this.el("main", null);
    root.append(main);
    const intro = this.el("div", null, {class: "intro"});
    const title = this.el("div", null);
    title.append(this.el("h2", "Receiver-Menü"),
      this.el("p", "Gestalte das Menü für deine Enigma2-Receiver."));
    intro.append(title, this.el("span", this.dirty ? "Ungespeicherte Änderungen" : this.model ? "Alle Änderungen gespeichert" : "", {class: "save-state", role: "status"}));
    main.append(intro, this.el("p", this.message, {class: "notice", role: "status", "aria-live": "polite"}));
    if (!this.model) return;

    const layout = this.el("div", null, {class: "editor-layout"});
    const menuColumn = this.el("div", null, {class: "column menu-column", tabindex: "0", role: "region", "aria-label": "Menüeinträge bearbeiten"});
    const toolsColumn = this.el("div", null, {class: "column tools-column", tabindex: "0", role: "region", "aria-label": "Menüeinstellungen"});
    layout.append(menuColumn, toolsColumn);
    main.append(layout);
    const current = this.path[this.path.length - 1];
    menuColumn.dataset.menuId = current.id;
    const menu = this.el("ha-card", null);
    const crumbs = this.el("nav", null, {class: "breadcrumbs", "aria-label": "Menüpfad"});
    this.path.forEach((node, index) => {
      if (index) crumbs.append(this.icon("chevron-right"));
      if (index === this.path.length - 1) {
        crumbs.append(this.el("span", node.label, {"aria-current": "page"}));
      } else crumbs.append(this.button(node.label, () => {
        this.path = this.path.slice(0, index + 1); this.render();
      }));
    });
    const heading = this.el("div", null, {class: "section-heading"});
    heading.append(this.el("h2", "Menüeinträge"), this.el("p", `Einträge in „${current.label}“ bearbeiten und sortieren.`));
    menu.append(crumbs, heading);
    if (!current.children.length) {
      const empty = this.el("div", null, {class: "empty"});
      empty.append(this.icon("format-list-bulleted"), this.el("strong", "Dieses Menü ist noch leer"),
        this.el("p", "Füge Entitäten oder Untermenüs hinzu, die auf dem Receiver erscheinen sollen."));
      menu.append(empty);
    }
    const entries = this.el("ul", null, {class: "entry-list", "aria-label": "Menüeinträge"});
    const sortable = this.el("ha-sortable", null);
    sortable.disabled = this.loading;
    sortable.rollback = true;
    sortable.handleSelector = ".drag-handle";
    sortable.draggableSelector = ".row";
    // Document hit testing sees the shadow host, so Sortable's automatic parent
    // detection misses the list. Scroll its actual viewport ourselves, including
    // while the pointer is held still; disable the competing library timer.
    sortable.options = {scroll: false};
    sortable.addEventListener("drag-start", event => {
      if (event.target === sortable && !this.loading && !this.confirmation) this.startDragScroll(sortable, menuColumn);
    });
    let pendingMove;
    sortable.addEventListener("item-moved", event => {
      event.stopPropagation();
      if (event.target === sortable) pendingMove = event.detail;
    });
    sortable.addEventListener("drag-end", event => {
      event.stopPropagation();
      if (event.target !== sortable) return;
      this.stopDragScroll?.();
      const move = pendingMove;
      pendingMove = undefined;
      // HA rolls the DOM back after drag-end; update the model/render afterwards.
      if (move) queueMicrotask(() => {
        if (sortable.isConnected) this.moveEntry(current, move.oldIndex, move.newIndex);
      });
    });
    current.children.forEach((node, index) => {
      const row = this.el("li", null, {class: "row", "data-node-id": node.id});
      const handle = this.el("div", null, {class: "drag-handle", role: "img",
        "aria-label": "Zum Sortieren ziehen", title: "Zum Sortieren ziehen", "aria-disabled": String(this.loading)});
      handle.append(this.icon("drag-horizontal-variant"));
      const icon = node.type === "menu" ? this.icon("folder-outline")
        : this.el("ha-state-icon", null, {"aria-hidden": "true", "data-entity-id": node.entity_id});
      icon.className = "entry-icon";
      const content = this.el("div", null, {class: "entry-content"});
      const name = this.field(content, "label-" + node.id, "Anzeigename", node.label, value => { node.label = value; });
      const rowActions = this.el("div", null, {class: "entry-actions"});
      if (node.type === "menu") {
        name.hint = `${node.children.length} ${node.children.length === 1 ? "Eintrag" : "Einträge"}`;
        rowActions.append(this.iconButton("Untermenü bearbeiten", "pencil", () => { this.path.push(node); this.render(); }));
      } else {
        name.dataset.entityId = node.entity_id;
        name.hint = this.entityDescription(node.entity_id);
      }
      const move = offset => this.moveEntry(current, index, index + offset);
      const remove = this.iconButton("Entfernen", "delete-outline", async () => {
        if (node.type === "menu" && node.children.length && !await this.confirmAction(
          "Untermenü mit allen Einträgen entfernen?", `„${node.label}“ und alle enthaltenen Einträge werden aus dem Receiver-Menü entfernt.`, "Untermenü entfernen")) return;
        const position = current.children.indexOf(node);
        if (!this.isConnected || this.loading || current !== this.path.at(-1) || position < 0) return;
        current.children.splice(position, 1); this.markDirty(); this.render();
      });
      remove.className = "danger";
      rowActions.append(this.iconButton("Nach oben", "arrow-up", () => move(-1), index === 0),
        this.iconButton("Nach unten", "arrow-down", () => move(1), index === current.children.length - 1), remove);
      row.append(handle, icon, content, rowActions);
      entries.append(row);
    });
    sortable.append(entries);
    menu.append(sortable);
    menuColumn.append(menu);
    this.updateEntryEntities();

    const display = this.card("Darstellung auf dem Receiver", "Titel und Schrift für das Receiver-Menü festlegen.");
    display.className = "receiver-display";
    const fields = this.el("div", null, {class: "card-body fields"});
    this.field(fields, "menu-title", "Menütitel", this.model.root.label, value => { this.model.root.label = value; });
    const fontOptions = [
      {value: "Regular", label: "Regular (Standard)"},
      {value: "Fixed", label: "Fixed (feste Zeichenbreite)"},
      {value: "Console", label: "Console"},
      {value: "Italic", label: "Italic (Skin-Schrift)"},
      {value: "Gradient_Font", label: "Gradient_Font (GradientFHD)"},
    ];
    const family = this.model.display.font_family;
    if (!fontOptions.some(option => option.value === family)) {
      fontOptions.push({value: family, label: family});
    }
    const font = this.selectionField(fields, "font-family", "Schriftfamilie", family, fontOptions,
      value => { this.model.display.font_family = value; });
    font.helper = "Verfügbarkeit abhängig vom Receiver-Skin. Ersatzschrift: Regular.";
    const sizes = Array.from({length: 49}, (_, index) => {
      const value = String(index + 16);
      return {value, label: value === "28" ? "28 (Standard)" : value};
    });
    const size = this.selectionField(fields, "font-size", "Schriftgröße", this.model.display.font_size, sizes,
      value => { this.model.display.font_size = Number(value); });
    size.helper = "Kann in den Receiver-Einstellungen überschrieben werden.";
    display.append(fields);

    const entity = this.card("Entität hinzufügen", "Wähle eine Entität aus Home Assistant aus.");
    const entityBody = this.el("div", null, {class: "card-body"});
    this.renderEntitySelection(entityBody, current);
    entity.append(entityBody);
    toolsColumn.append(entity);

    const submenu = this.card("Untermenü hinzufügen", "Gruppiere Einträge zum Beispiel nach Raum oder Funktion.");
    const addMenu = this.el("div", null, {class: "card-body menu-add"});
    const menuName = this.textField("new-menu", "Name des Untermenüs", this.menuDraft,
      value => {
        this.menuDraft = typeof value === "string" ? value : "";
        addMenuButton.disabled = this.loading || this.path.length >= 9 || !this.menuDraft.trim();
      }, {required: false});
    menuName.disabled = this.loading || this.path.length >= 9;
    const addMenuButton = this.button("Untermenü hinzufügen", () => {
      if (!this.menuDraft.trim()) return;
      const node = {type: "menu", id: this.id(), label: this.menuDraft.trim(), children: []};
      current.children.push(node);
      this.menuDraft = "";
      this.markDirty(); this.render();
      this.revealEntry(node.id);
    }, this.path.length >= 9 || !this.menuDraft.trim(), "filled");
    addMenu.append(menuName, addMenuButton);
    submenu.append(addMenu);
    if (this.path.length >= 9) {
      entityBody.prepend(this.el("p", "Die maximale Menütiefe ist erreicht. Wechsle zum Hinzufügen eine Ebene zurück.", {class: "depth-notice"}));
    }
    toolsColumn.append(submenu, display);
    // Refreshes (filters, save, deletion) must not reset either scroll region.
    // Entering another menu starts at its first entry.
    if (previousMenu?.dataset.menuId === current.id) menuColumn.scrollTop = menuScroll;
    toolsColumn.scrollTop = toolsScroll;
  }
}
if (!customElements.get("enigmaha-panel")) customElements.define("enigmaha-panel", EnigmaHAPanel);
