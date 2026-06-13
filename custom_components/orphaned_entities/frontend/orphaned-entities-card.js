/**
 * Orphaned Entities Card
 * Lovelace card for ha-orphaned-entities integration
 * @version 1.1.0
 */

const CARD_VERSION = "1.1.0";
const DOMAIN = "orphaned_entities";

const REASON_LABELS = {
  device_missing:        "Gerät fehlt",
  no_state:              "Kein Status",
  no_integration:        "Keine Integration",
  no_device_no_platform: "Kein Gerät / keine Plattform",
};

function reasonLabel(reason) {
  if (reason.startsWith("unavailable_")) {
    const days = reason.split("_")[1];
    return `Nicht verfügbar seit ${days}`;
  }
  if (reason.startsWith("stale_")) {
    const days = reason.split("_")[1];
    return `Inaktiv seit ${days} Tagen (Integration vorhanden)`;
  }
  return REASON_LABELS[reason] || reason;
}

class OrphanedEntitiesCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._entities = [];       // scan results (active orphans)
    this._ignored  = [];       // ignored entity_ids from backend
    this._selected = new Set();
    this._filter   = "";
    this._sortBy   = "domain";
    this._tab      = "orphans"; // "orphans" | "ignored"
    this._loading  = false;
    this._message  = null;
    this._confirmAction = null;
    this._initialized   = false;
  }

  setConfig(config) { this._config = config; }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialized = true;
      this._render(); // initial render only
      this._subscribeEvents();
      this._loadResults();
    }
    // Do NOT re-render on every hass update — only event callbacks trigger render
  }

  _subscribeEvents() {
    try {
      this._hass.connection.subscribeEvents((event) => {
        this._entities = event.data.entities || [];
        this._ignored  = event.data.ignored  || [];
        this._loading  = false;
        this._render();
      }, `${DOMAIN}_results`);
    } catch (e) {
      console.warn("orphaned-entities-card: subscribeEvents failed", e);
    }
  }

  async _loadResults() {
    this._loading = true;
    this._render();
    try {
      await this._hass.callService(DOMAIN, "get_results", {});
    } catch (e) {
      this._message = { type: "error", text: "Fehler beim Laden: " + e.message };
      this._loading = false;
      this._render();
      return;
    }
    // Retry after 3s if still no results (event may have been missed)
    setTimeout(async () => {
      if (this._entities.length === 0 && !this._loading) {
        try {
          await this._hass.callService(DOMAIN, "get_results", {});
        } catch (_) {}
      }
    }, 3000);
  }

  async _rescan() {
    this._loading = true;
    this._message = null;
    this._render();
    try {
      await this._hass.callService(DOMAIN, "rescan", {});
    } catch (e) {
      this._message = { type: "error", text: "Fehler beim Scan: " + e.message };
      this._loading = false;
      this._render();
    }
  }

  // ── Main-tab actions ──────────────────────────────────────────────────────

  async _performAction(action) {
    if (this._selected.size === 0) {
      this._message = { type: "warning", text: "Keine Entitäten ausgewählt." };
      this._render();
      return;
    }
    if (action === "delete") {
      this._confirmAction = action;
      this._render();
      return;
    }
    await this._executeAction(action);
  }

  async _executeAction(action) {
    this._loading = true;
    this._message = null;
    this._confirmAction = null;
    this._render();

    const serviceName =
      action === "disable" ? "disable_entity" :
      action === "delete"  ? "delete_entity"  :
      action === "ignore"  ? "ignore_entity"  : null;
    if (!serviceName) return;

    let ok = 0, err = 0;
    for (const entityId of this._selected) {
      try {
        await this._hass.callService(DOMAIN, serviceName, { entity_id: entityId });
        ok++;
      } catch (e) {
        err++;
        console.error(`Error ${action} ${entityId}:`, e);
      }
    }

    this._selected.clear();
    const verb = action === "disable" ? "deaktiviert" : action === "delete" ? "gelöscht" : "ignoriert";
    this._message = {
      type: err === 0 ? "success" : "warning",
      text: `${ok} Entität(en) ${verb}.${err > 0 ? ` ${err} Fehler.` : ""}`,
    };
    // Backend fires updated results event automatically for ignore;
    // for disable/delete we trigger get_results manually
    if (action !== "ignore") {
      await this._hass.callService(DOMAIN, "get_results", {});
    }
  }

  // ── Ignored-tab action ────────────────────────────────────────────────────

  async _unignoreSelected() {
    if (this._selectedIgnored.size === 0) {
      this._message = { type: "warning", text: "Keine Entitäten ausgewählt." };
      this._render();
      return;
    }
    this._loading = true;
    this._message = null;
    this._render();

    let ok = 0, err = 0;
    for (const entityId of this._selectedIgnored) {
      try {
        await this._hass.callService(DOMAIN, "unignore_entity", { entity_id: entityId });
        ok++;
      } catch (e) {
        err++;
      }
    }
    this._selectedIgnored.clear();
    this._message = {
      type: err === 0 ? "success" : "warning",
      text: `${ok} Entität(en) wieder in Auswertung aufgenommen.${err > 0 ? ` ${err} Fehler.` : ""}`,
    };
    // Backend fires updated results event; loading will clear after event arrives
  }

  // ── Selection helpers ─────────────────────────────────────────────────────

  get _selectedIgnored() {
    if (!this.__selectedIgnored) this.__selectedIgnored = new Set();
    return this.__selectedIgnored;
  }

  _toggleSelect(entityId) {
    if (this._selected.has(entityId)) this._selected.delete(entityId);
    else this._selected.add(entityId);
    this._render();
  }

  _toggleSelectAll() {
    const f = this._filteredEntities();
    if (this._selected.size === f.length) this._selected.clear();
    else f.forEach(e => this._selected.add(e.entity_id));
    this._render();
  }

  _toggleSelectIgnored(entityId) {
    if (this._selectedIgnored.has(entityId)) this._selectedIgnored.delete(entityId);
    else this._selectedIgnored.add(entityId);
    this._render();
  }

  _toggleSelectAllIgnored() {
    const f = this._filteredIgnored();
    if (this._selectedIgnored.size === f.length) this._selectedIgnored.clear();
    else f.forEach(id => this._selectedIgnored.add(id));
    this._render();
  }

  // ── Filtering ─────────────────────────────────────────────────────────────

  _filteredEntities() {
    const f = this._filter.toLowerCase();
    return this._entities
      .filter(e =>
        !f ||
        e.entity_id.toLowerCase().includes(f) ||
        (e.name || "").toLowerCase().includes(f) ||
        e.domain.toLowerCase().includes(f)
      )
      .sort((a, b) => {
        if (this._sortBy === "domain") return a.domain.localeCompare(b.domain) || a.entity_id.localeCompare(b.entity_id);
        if (this._sortBy === "name")   return (a.name || a.entity_id).localeCompare(b.name || b.entity_id);
        if (this._sortBy === "state")  return a.state.localeCompare(b.state);
        return 0;
      });
  }

  _filteredIgnored() {
    const f = this._filter.toLowerCase();
    return this._ignored.filter(id => !f || id.toLowerCase().includes(f)).sort();
  }

  // ── Rendering ─────────────────────────────────────────────────────────────

  _render() {
    const CSS = `
      <style>
        :host { display: block; }
        ha-card { padding: 0; overflow: hidden; }
        .loading-bar {
          height: 3px; overflow: hidden;
          background: linear-gradient(90deg, var(--primary-color) 0%, transparent 100%);
          animation: loading 1.2s ease-in-out infinite;
        }
        @keyframes loading { 0% { transform:translateX(-100%); } 100% { transform:translateX(200%); } }

        /* Header */
        .header {
          display: flex; align-items: center; justify-content: space-between;
          padding: 16px 16px 8px; border-bottom: 1px solid var(--divider-color);
          flex-wrap: wrap; gap: 8px;
        }
        .title { font-size: 1.1em; font-weight: 600; color: var(--primary-text-color); display: flex; align-items: center; gap: 8px; }
        .badge { background: var(--error-color); color: white; border-radius: 12px; padding: 2px 8px; font-size: 0.8em; font-weight: 700; }
        .badge-ignored { background: #9e9e9e; }

        /* Tabs */
        .tabs { display: flex; border-bottom: 1px solid var(--divider-color); }
        .tab { flex: 1; padding: 10px 8px; text-align: center; cursor: pointer; font-size: 0.88em; font-weight: 500; color: var(--secondary-text-color); border-bottom: 2px solid transparent; transition: all 0.2s; user-select: none; }
        .tab.active { color: var(--primary-color); border-bottom-color: var(--primary-color); }
        .tab:hover:not(.active) { background: var(--secondary-background-color); }

        /* Toolbar */
        .toolbar { display: flex; gap: 8px; padding: 8px 16px; align-items: center; flex-wrap: wrap; border-bottom: 1px solid var(--divider-color); }
        .toolbar input[type=text] { flex: 1; min-width: 120px; border: 1px solid var(--divider-color); border-radius: 4px; padding: 6px 10px; background: var(--card-background-color); color: var(--primary-text-color); font-size: 0.9em; }
        .toolbar select { border: 1px solid var(--divider-color); border-radius: 4px; padding: 6px; background: var(--card-background-color); color: var(--primary-text-color); font-size: 0.9em; }

        /* Action bar */
        .action-bar { display: flex; gap: 8px; padding: 8px 16px; border-bottom: 1px solid var(--divider-color); flex-wrap: wrap; align-items: center; }
        .action-bar .info { font-size: 0.85em; color: var(--secondary-text-color); flex: 1; }

        /* Buttons */
        button { padding: 6px 14px; border-radius: 4px; border: none; cursor: pointer; font-size: 0.85em; font-weight: 500; transition: opacity 0.2s; }
        button:disabled { opacity: 0.4; cursor: default; }
        .btn-disable  { background: var(--warning-color, #ff9800); color: white; }
        .btn-delete   { background: var(--error-color, #db4437); color: white; }
        .btn-ignore   { background: #4fc3f7; color: white; }
        .btn-unignore { background: #4caf50; color: white; }
        .btn-scan     { background: var(--primary-color); color: white; }
        .btn-secondary { background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color); }

        /* Select-all row */
        .select-all-row { display: flex; align-items: center; gap: 8px; padding: 8px 16px; border-bottom: 1px solid var(--divider-color); font-size: 0.85em; color: var(--secondary-text-color); cursor: pointer; user-select: none; }
        .select-all-row:hover { background: var(--secondary-background-color); }

        /* Entity list */
        .entity-list { max-height: 500px; overflow-y: auto; }
        .entity-row { display: flex; align-items: flex-start; padding: 10px 16px; border-bottom: 1px solid var(--divider-color); gap: 12px; cursor: pointer; transition: background 0.15s; }
        .entity-row:hover   { background: var(--secondary-background-color); }
        .entity-row.selected { background: rgba(var(--rgb-primary-color,3,169,244), 0.08); }
        .entity-row input[type=checkbox] { margin-top: 3px; cursor: pointer; width: 16px; height: 16px; flex-shrink: 0; }
        .entity-info { flex: 1; min-width: 0; }
        .entity-name { font-weight: 500; font-size: 0.9em; color: var(--primary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .entity-id   { font-size: 0.78em; color: var(--secondary-text-color); font-family: monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .entity-meta { display: flex; gap: 6px; margin-top: 4px; flex-wrap: wrap; }

        /* Chips */
        .chip { font-size: 0.72em; padding: 2px 7px; border-radius: 10px; font-weight: 500; }
        .chip-domain    { background: var(--secondary-background-color); color: var(--secondary-text-color); border: 1px solid var(--divider-color); }
        .chip-reason    { background: rgba(219,68,55,0.12); color: var(--error-color, #db4437); }
        .chip-unavail   { background: rgba(255,152,0,0.15); color: var(--warning-color, #ff9800); }
        .chip-ok        { background: rgba(76,175,80,0.12); color: var(--success-color, #4caf50); }
        .chip-ignored   { background: rgba(158,158,158,0.15); color: #757575; }

        /* Message */
        .message { margin: 8px 16px; padding: 10px 14px; border-radius: 6px; font-size: 0.88em; }
        .message.error   { background: rgba(219,68,55,0.12);  color: var(--error-color,   #db4437); }
        .message.success { background: rgba(76,175,80,0.12);   color: var(--success-color, #4caf50); }
        .message.warning { background: rgba(255,152,0,0.12);   color: var(--warning-color, #ff9800); }

        .empty { padding: 32px 16px; text-align: center; color: var(--secondary-text-color); font-size: 0.9em; }

        /* Confirm dialog */
        .confirm-dialog { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 999; }
        .confirm-box { background: var(--card-background-color); border-radius: 12px; padding: 24px; max-width: 360px; width: 90%; box-shadow: 0 8px 32px rgba(0,0,0,0.3); }
        .confirm-box h3 { margin: 0 0 12px; font-size: 1em; }
        .confirm-box p  { margin: 0 0 20px; font-size: 0.88em; color: var(--secondary-text-color); }
        .confirm-actions { display: flex; gap: 8px; justify-content: flex-end; }

        /* Ignored row (simpler, no reasons) */
        .ignored-row { display: flex; align-items: center; padding: 10px 16px; border-bottom: 1px solid var(--divider-color); gap: 12px; cursor: pointer; transition: background 0.15s; }
        .ignored-row:hover    { background: var(--secondary-background-color); }
        .ignored-row.selected { background: rgba(var(--rgb-primary-color,3,169,244), 0.08); }
        .ignored-row input[type=checkbox] { cursor: pointer; width: 16px; height: 16px; flex-shrink: 0; }
        .ignored-id { font-size: 0.82em; font-family: monospace; color: var(--primary-text-color); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .ignored-domain { font-size: 0.72em; padding: 2px 7px; border-radius: 10px; background: rgba(158,158,158,0.15); color: #757575; font-weight: 500; }
      </style>
    `;

    const filtered        = this._filteredEntities();
    const filteredIgnored = this._filteredIgnored();
    const allSelected     = filtered.length > 0 && this._selected.size === filtered.length;
    const allIgnSel       = filteredIgnored.length > 0 && this._selectedIgnored.size === filteredIgnored.length;

    this.shadowRoot.innerHTML = `
      ${CSS}
      <ha-card>
        ${this._loading ? '<div class="loading-bar"></div>' : ""}

        <div class="header">
          <div class="title">
            🧹 Verwaiste Entitäten
            ${this._entities.length > 0 ? `<span class="badge">${this._entities.length}</span>` : ""}
            ${this._ignored.length  > 0 ? `<span class="badge badge-ignored" title="Ignorierte Entitäten">${this._ignored.length} ignoriert</span>` : ""}
          </div>
          <button class="btn-scan" id="btn-rescan">🔄 Neu scannen</button>
        </div>

        <div class="tabs">
          <div class="tab ${this._tab === "orphans" ? "active" : ""}" id="tab-orphans">
            🔍 Verwaist (${this._entities.length})
          </div>
          <div class="tab ${this._tab === "ignored" ? "active" : ""}" id="tab-ignored">
            👁 Ignoriert (${this._ignored.length})
          </div>
        </div>

        ${this._message ? `<div class="message ${this._message.type}">${this._message.text}</div>` : ""}

        ${this._tab === "orphans"
          ? this._renderOrphansTab(filtered, allSelected)
          : this._renderIgnoredTab(filteredIgnored, allIgnSel)
        }
      </ha-card>

      ${this._confirmAction ? `
        <div class="confirm-dialog">
          <div class="confirm-box">
            <h3>⚠️ Löschen bestätigen</h3>
            <p>${this._selected.size} Entität(en) werden dauerhaft aus der Registry entfernt. Dies kann nicht rückgängig gemacht werden.</p>
            <div class="confirm-actions">
              <button class="btn-secondary" id="btn-cancel">Abbrechen</button>
              <button class="btn-delete" id="btn-confirm-delete">Endgültig löschen</button>
            </div>
          </div>
        </div>
      ` : ""}
    `;

    this._attachEvents();
  }

  _renderOrphansTab(filtered, allSelected) {
    return `
      <div class="toolbar">
        <input type="text" id="search" placeholder="Suchen nach ID, Name, Domain…" value="${this._filter}">
        <select id="sort">
          <option value="domain" ${this._sortBy === "domain" ? "selected" : ""}>Sortierung: Domain</option>
          <option value="name"   ${this._sortBy === "name"   ? "selected" : ""}>Sortierung: Name</option>
          <option value="state"  ${this._sortBy === "state"  ? "selected" : ""}>Sortierung: Status</option>
        </select>
      </div>

      <div class="action-bar">
        <span class="info">${this._selected.size} von ${filtered.length} ausgewählt</span>
        <button class="btn-disable" id="btn-disable" ${this._selected.size === 0 ? "disabled" : ""}>⏸ Deaktivieren</button>
        <button class="btn-delete"  id="btn-delete"  ${this._selected.size === 0 ? "disabled" : ""}>🗑 Löschen</button>
        <button class="btn-ignore"  id="btn-ignore"  ${this._selected.size === 0 ? "disabled" : ""}>👁 Ignorieren</button>
      </div>

      <div class="select-all-row" id="select-all">
        <input type="checkbox" ${allSelected ? "checked" : ""}>
        Alle auswählen (${filtered.length})
      </div>

      <div class="entity-list">
        ${filtered.length === 0 ? `
          <div class="empty">
            ${this._loading
              ? "Lade Ergebnisse…"
              : this._entities.length === 0
                ? "✅ Keine verwaisten Entitäten gefunden."
                : "Keine Ergebnisse für die aktuelle Suche."
            }
          </div>
        ` : filtered.map(e => this._renderOrphanRow(e)).join("")}
      </div>
    `;
  }

  _renderIgnoredTab(filteredIgnored, allIgnSel) {
    return `
      <div class="toolbar">
        <input type="text" id="search-ignored" placeholder="Suchen nach Entity-ID…" value="${this._filter}">
      </div>

      <div class="action-bar">
        <span class="info">${this._selectedIgnored.size} von ${filteredIgnored.length} ausgewählt</span>
        <button class="btn-unignore" id="btn-unignore" ${this._selectedIgnored.size === 0 ? "disabled" : ""}>
          ↩ Wieder auswerten
        </button>
      </div>

      <div class="select-all-row" id="select-all-ignored">
        <input type="checkbox" ${allIgnSel ? "checked" : ""}>
        Alle auswählen (${filteredIgnored.length})
      </div>

      <div class="entity-list">
        ${filteredIgnored.length === 0 ? `
          <div class="empty">
            ${this._ignored.length === 0
              ? "Keine ignorierten Entitäten vorhanden."
              : "Keine Ergebnisse für die aktuelle Suche."
            }
          </div>
        ` : filteredIgnored.map(id => this._renderIgnoredRow(id)).join("")}
      </div>
    `;
  }

  _renderOrphanRow(e) {
    const selected = this._selected.has(e.entity_id);
    const stateClass = (e.state === "unavailable" || e.state === "unknown" || e.state === "not_found")
      ? "chip-unavail" : "chip-ok";
    return `
      <div class="entity-row ${selected ? "selected" : ""}" data-entity="${e.entity_id}">
        <input type="checkbox" data-cb="${e.entity_id}" ${selected ? "checked" : ""}>
        <div class="entity-info">
          <div class="entity-name">${e.name || e.entity_id}</div>
          <div class="entity-id">${e.entity_id}</div>
          <div class="entity-meta">
            <span class="chip chip-domain">${e.domain}</span>
            <span class="chip ${stateClass}">${e.state}</span>
            ${e.reasons.map(r => `<span class="chip chip-reason">${reasonLabel(r)}</span>`).join("")}
          </div>
        </div>
      </div>
    `;
  }

  _renderIgnoredRow(entityId) {
    const selected = this._selectedIgnored.has(entityId);
    const domain = entityId.split(".")[0];
    return `
      <div class="ignored-row ${selected ? "selected" : ""}" data-ign="${entityId}">
        <input type="checkbox" data-ign-cb="${entityId}" ${selected ? "checked" : ""}>
        <span class="ignored-id">${entityId}</span>
        <span class="ignored-domain">${domain}</span>
      </div>
    `;
  }

  // ── Event wiring ──────────────────────────────────────────────────────────

  _attachEvents() {
    const root = this.shadowRoot;

    // Header
    root.getElementById("btn-rescan")?.addEventListener("click", () => this._rescan());

    // Tabs
    root.getElementById("tab-orphans")?.addEventListener("click", () => {
      this._tab = "orphans";
      this._filter = "";
      this._selected.clear();
      this._render();
    });
    root.getElementById("tab-ignored")?.addEventListener("click", () => {
      this._tab = "ignored";
      this._filter = "";
      this._selectedIgnored.clear();
      this._render();
    });

    // Orphans tab
    root.getElementById("btn-disable")?.addEventListener("click", () => this._performAction("disable"));
    root.getElementById("btn-delete")?.addEventListener("click",  () => this._performAction("delete"));
    root.getElementById("btn-ignore")?.addEventListener("click",  () => this._performAction("ignore"));
    root.getElementById("select-all")?.addEventListener("click",  () => this._toggleSelectAll());
    root.getElementById("search")?.addEventListener("input", e => { this._filter = e.target.value; this._render(); });
    root.getElementById("sort")?.addEventListener("change",  e => { this._sortBy = e.target.value; this._render(); });

    root.querySelectorAll("[data-cb]").forEach(cb => {
      cb.addEventListener("change", e => { e.stopPropagation(); this._toggleSelect(cb.dataset.cb); });
    });
    root.querySelectorAll(".entity-row").forEach(row => {
      row.addEventListener("click", e => { if (e.target.tagName === "INPUT") return; this._toggleSelect(row.dataset.entity); });
    });

    // Ignored tab
    root.getElementById("btn-unignore")?.addEventListener("click", () => this._unignoreSelected());
    root.getElementById("select-all-ignored")?.addEventListener("click", () => this._toggleSelectAllIgnored());
    root.getElementById("search-ignored")?.addEventListener("input", e => { this._filter = e.target.value; this._render(); });

    root.querySelectorAll("[data-ign-cb]").forEach(cb => {
      cb.addEventListener("change", e => { e.stopPropagation(); this._toggleSelectIgnored(cb.dataset.ignCb); });
    });
    root.querySelectorAll(".ignored-row").forEach(row => {
      row.addEventListener("click", e => { if (e.target.tagName === "INPUT") return; this._toggleSelectIgnored(row.dataset.ign); });
    });

    // Confirm dialog
    root.getElementById("btn-cancel")?.addEventListener("click", () => { this._confirmAction = null; this._render(); });
    root.getElementById("btn-confirm-delete")?.addEventListener("click", () => this._executeAction("delete"));
  }

  getCardSize() { return 6; }
  static getStubConfig() { return {}; }
}

customElements.define("orphaned-entities-card", OrphanedEntitiesCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "orphaned-entities-card",
  name: "Orphaned Entities Card",
  description: "Zeigt verwaiste Entitäten – Deaktivieren, Löschen, Ignorieren. Tab für ignorierte Entitäten zum Wiederherstellen.",
  preview: false,
});

console.info(
  `%c ORPHANED-ENTITIES-CARD %c v${CARD_VERSION} `,
  "color: white; background: #db4437; font-weight: 700;",
  "color: #db4437; background: white; font-weight: 700;"
);
