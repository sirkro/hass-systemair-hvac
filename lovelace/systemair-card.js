/**
 * Systemair HVAC Custom Lovelace Card
 *
 * A compact, collapsible card for the systemair Home Assistant integration.
 * Shows temperature control, fan/preset modes, air quality sensors,
 * timed mode launchers, alarm indicators, and ECO mode toggle.
 *
 * Installation:
 *   1. Copy this file to /config/www/systemair-card.js
 *   2. Add resource in Lovelace:
 *        url: /local/systemair-card.js
 *        type: module
 *   3. Add the card to a dashboard (see systemair-dashboard.yaml for a full example)
 *
 * Config options:
 *   type: custom:systemair-card
 *   title: "Systemair HVAC"          # optional, default "Systemair HVAC"
 *   entity: climate.systemair_hvac   # climate entity (required)
 *   name_prefix: systemair           # entity name prefix, default "systemair"
 *   show_alarms: true                # show alarm section, default true
 *   show_functions: true             # show active functions section, default true
 */

const CARD_VERSION = "1.0.0";

const css = `
  :host {
    --sa-primary: #1976d2;
    --sa-accent: #42a5f5;
    --sa-bg: var(--card-background-color, #fff);
    --sa-surface: var(--secondary-background-color, #f5f5f5);
    --sa-text: var(--primary-text-color, #212121);
    --sa-sub: var(--secondary-text-color, #757575);
    --sa-border: var(--divider-color, #e0e0e0);
    --sa-green: #43a047;
    --sa-red: #e53935;
    --sa-orange: #fb8c00;
    --sa-yellow: #fdd835;
    --sa-radius: 12px;
    --sa-chip-radius: 16px;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  .card {
    background: var(--sa-bg);
    border-radius: var(--sa-radius);
    font-family: var(--paper-font-body1_-_font-family, sans-serif);
    color: var(--sa-text);
    overflow: hidden;
  }

  /* ── Header ── */
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 16px 10px;
    cursor: pointer;
    user-select: none;
    border-bottom: 1px solid var(--sa-border);
  }
  .header-left { display: flex; align-items: center; gap: 10px; }
  .header-icon { width: 36px; height: 36px; flex-shrink: 0; }
  .header-title { font-size: 1rem; font-weight: 600; }
  .header-subtitle { font-size: 0.75rem; color: var(--sa-sub); margin-top: 1px; }
  .header-right { display: flex; align-items: center; gap: 8px; }
  .alarm-badge {
    background: var(--sa-red);
    color: #fff;
    border-radius: 10px;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 2px 7px;
    min-width: 22px;
    text-align: center;
  }
  .collapse-icon { color: var(--sa-sub); transition: transform 0.2s; }
  .collapse-icon.open { transform: rotate(180deg); }

  /* ── Body ── */
  .body { padding: 0 16px 16px; }

  /* ── Section ── */
  .section { margin-top: 14px; }
  .section-label {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--sa-sub);
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    user-select: none;
  }
  .section-label .chevron { transition: transform 0.2s; }
  .section-label .chevron.open { transform: rotate(180deg); }
  .section-content { }
  .section-content.hidden { display: none; }

  /* ── Temperature control ── */
  .temp-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .temp-display {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 80px;
  }
  .temp-current {
    font-size: 2.4rem;
    font-weight: 300;
    line-height: 1;
    color: var(--sa-primary);
  }
  .temp-current sup { font-size: 1rem; }
  .temp-label { font-size: 0.68rem; color: var(--sa-sub); margin-top: 2px; }

  .temp-setpoint {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
  }
  .temp-sp-label { font-size: 0.68rem; color: var(--sa-sub); }
  .temp-sp-controls {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .sp-btn {
    width: 32px; height: 32px;
    border-radius: 50%;
    border: 2px solid var(--sa-border);
    background: transparent;
    color: var(--sa-text);
    font-size: 1.2rem;
    font-weight: 700;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.15s, border-color 0.15s;
  }
  .sp-btn:hover { background: var(--sa-surface); border-color: var(--sa-primary); }
  .sp-value {
    font-size: 1.4rem;
    font-weight: 600;
    min-width: 44px;
    text-align: center;
  }

  /* ── Chip rows ── */
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .chip {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    border-radius: var(--sa-chip-radius);
    font-size: 0.78rem;
    font-weight: 500;
    background: var(--sa-surface);
    border: 1.5px solid transparent;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
  }
  .chip:hover { background: var(--sa-border); }
  .chip.active {
    background: var(--sa-primary);
    color: #fff;
    border-color: var(--sa-primary);
  }
  .chip ha-icon { --mdc-icon-size: 14px; }

  /* ── Fan speed bar ── */
  .fan-bar-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 2px;
  }
  .fan-bar-wrap { flex: 1; }
  .fan-bar-bg {
    height: 6px;
    border-radius: 3px;
    background: var(--sa-border);
    overflow: hidden;
  }
  .fan-bar-fill {
    height: 100%;
    border-radius: 3px;
    background: linear-gradient(90deg, var(--sa-accent), var(--sa-primary));
    transition: width 0.5s;
  }
  .fan-bar-val { font-size: 0.85rem; font-weight: 600; min-width: 38px; text-align: right; color: var(--sa-sub); }

  /* ── Sensor grid ── */
  .sensor-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(90px, 1fr));
    gap: 8px;
  }
  .sensor-tile {
    background: var(--sa-surface);
    border-radius: 8px;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .sensor-icon { --mdc-icon-size: 18px; color: var(--sa-sub); }
  .sensor-val { font-size: 1.05rem; font-weight: 600; line-height: 1; }
  .sensor-lbl { font-size: 0.65rem; color: var(--sa-sub); }

  /* ── Timed modes ── */
  .timed-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
    gap: 8px;
  }
  .timed-btn {
    background: var(--sa-surface);
    border: 1.5px solid var(--sa-border);
    border-radius: 8px;
    padding: 8px;
    cursor: pointer;
    text-align: center;
    transition: background 0.15s, border-color 0.15s;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
  }
  .timed-btn:hover { background: var(--sa-border); border-color: var(--sa-primary); }
  .timed-btn.active { border-color: var(--sa-accent); background: rgba(66,165,245,0.12); }
  .timed-btn ha-icon { --mdc-icon-size: 22px; color: var(--sa-primary); }
  .timed-name { font-size: 0.72rem; font-weight: 600; color: var(--sa-text); }
  .timed-duration { font-size: 0.65rem; color: var(--sa-sub); }
  .remaining-badge {
    background: var(--sa-accent);
    color: #fff;
    border-radius: 8px;
    font-size: 0.65rem;
    padding: 1px 5px;
    margin-top: 2px;
  }

  /* ── ECO + status row ── */
  .eco-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .eco-toggle {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
  }
  .eco-label { font-size: 0.85rem; font-weight: 500; }
  .toggle-track {
    width: 42px; height: 24px;
    border-radius: 12px;
    background: var(--sa-border);
    position: relative;
    transition: background 0.2s;
    cursor: pointer;
    flex-shrink: 0;
  }
  .toggle-track.on { background: var(--sa-green); }
  .toggle-thumb {
    width: 20px; height: 20px;
    border-radius: 50%;
    background: #fff;
    position: absolute;
    top: 2px; left: 2px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    transition: transform 0.2s;
  }
  .toggle-track.on .toggle-thumb { transform: translateX(18px); }

  /* ── Alarms ── */
  .alarm-list { display: flex; flex-direction: column; gap: 5px; }
  .alarm-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 10px;
    border-radius: 6px;
    background: rgba(229,57,53,0.08);
    border: 1px solid rgba(229,57,53,0.25);
    font-size: 0.8rem;
  }
  .alarm-item ha-icon { --mdc-icon-size: 16px; color: var(--sa-red); flex-shrink: 0; }
  .alarm-none { font-size: 0.8rem; color: var(--sa-sub); padding: 4px 0; }

  /* ── Functions ── */
  .function-chips { display: flex; flex-wrap: wrap; gap: 5px; }
  .fn-chip {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 3px 9px;
    border-radius: var(--sa-chip-radius);
    font-size: 0.73rem;
    font-weight: 500;
    border: 1.5px solid var(--sa-border);
    color: var(--sa-sub);
  }
  .fn-chip.active {
    border-color: var(--sa-green);
    background: rgba(67,160,71,0.1);
    color: var(--sa-green);
  }
  .fn-chip ha-icon { --mdc-icon-size: 13px; }

  /* ── Divider ── */
  .divider { border: none; border-top: 1px solid var(--sa-border); margin: 12px 0; }
`;

// ── Helpers ────────────────────────────────────────────────────────────────

function stateOrUnavailable(hass, entityId) {
  if (!entityId) return null;
  const s = hass.states[entityId];
  if (!s || s.state === "unavailable" || s.state === "unknown") return null;
  return s;
}

function numVal(hass, entityId) {
  const s = stateOrUnavailable(hass, entityId);
  if (!s) return null;
  const v = parseFloat(s.state);
  return isNaN(v) ? null : v;
}

function strVal(hass, entityId) {
  const s = stateOrUnavailable(hass, entityId);
  return s ? s.state : null;
}

function fmt(v, decimals = 1, unit = "") {
  if (v === null || v === undefined) return "—";
  return `${parseFloat(v).toFixed(decimals)}${unit ? "\u202f" + unit : ""}`;
}

function eid(prefix, suffix) {
  return `${prefix}_${suffix}`;
}

// ── Card definition ─────────────────────────────────────────────────────────

class SystemairCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._collapsed = {};   // section collapse state
    this._spTemp = null;    // local setpoint override while sliding
    this._rendered = false;
  }

  static getConfigElement() {
    return document.createElement("div");
  }

  static getStubConfig() {
    return {
      type: "custom:systemair-card",
      entity: "climate.systemair_hvac",
      title: "Systemair HVAC",
      show_alarms: true,
      show_functions: true,
    };
  }

  setConfig(config) {
    if (!config.entity) throw new Error("'entity' (climate entity) is required");
    this._config = {
      title: "Systemair HVAC",
      show_alarms: true,
      show_functions: true,
      ...config,
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  // ── Data extraction ──────────────────────────────────────────────────────

  _data() {
    const hass = this._hass;
    const cfg = this._config;
    if (!hass) return null;

    const climateState = hass.states[cfg.entity];

    const currentTemp = climateState?.attributes?.current_temperature ?? null;
    const targetTemp = climateState?.attributes?.temperature ?? null;
    const hvacMode = climateState?.state ?? null;
    const hvacAction = climateState?.attributes?.hvac_action ?? null;
    const fanMode = climateState?.attributes?.fan_mode ?? null;
    const presetMode = climateState?.attributes?.preset_mode ?? null;
    const availableFanModes = climateState?.attributes?.fan_modes ?? ["low", "medium", "high"];
    const availablePresets = climateState?.attributes?.preset_modes ?? [];

    // Build a translation_key -> entity_id map for all entities on the same device.
    // hass.entities is the live entity registry available in Lovelace.
    const climateEntry = hass.entities?.[cfg.entity];
    const deviceId = climateEntry?.device_id;
    const byKey = {};  // translation_key -> entity_id
    const fnEntityIds = [];
    const alarmEntityIds = [];
    if (deviceId && hass.entities) {
      for (const [eid, entry] of Object.entries(hass.entities)) {
        if (entry.device_id !== deviceId) continue;
        if (entry.translation_key) byKey[entry.translation_key] = eid;
        if (entry.translation_key?.startsWith("function_")) fnEntityIds.push(eid);
        if (entry.translation_key?.startsWith("alarm_")) alarmEntityIds.push(eid);
      }
    }

    // Fallback: if hass.entities unavailable, derive prefix from climate entity_id
    // e.g. "climate.systemair_cloud_heime" -> "systemair_cloud_heime"
    const p = cfg.name_prefix ?? cfg.entity.replace(/^climate\./, "");

    function byKeyOrPrefix(translationKey, platform, prefixSuffix) {
      return byKey[translationKey] ?? `${platform}.${p}_${prefixSuffix}`;
    }

    // Sensors
    const sensorLookups = {
      supplyTemp:   byKeyOrPrefix("supply_air_temperature", "sensor", "supply_air_temperature"),
      outdoorTemp:  byKeyOrPrefix("outdoor_air_temperature", "sensor", "outdoor_air_temperature"),
      extractTemp:  byKeyOrPrefix("extract_air_temperature", "sensor", "extract_air_temperature"),
      humidity:     byKeyOrPrefix("humidity",                "sensor", "humidity"),
      co2:          byKeyOrPrefix("co2",                     "sensor", "co2"),
      safSpeed:     byKeyOrPrefix("saf_speed",               "sensor", "saf_speed"),
      eafSpeed:     byKeyOrPrefix("eaf_speed",               "sensor", "eaf_speed"),
      safRpm:       byKeyOrPrefix("saf_rpm",                 "sensor", "saf_rpm"),
      eafRpm:       byKeyOrPrefix("eaf_rpm",                 "sensor", "eaf_rpm"),
      filterDays:   byKeyOrPrefix("filter_days_left",        "sensor", "filter_days_left"),
      remainingMin: byKeyOrPrefix("remaining_time",          "sensor", "remaining_time"),
      userModeName: byKeyOrPrefix("user_mode",               "sensor", "user_mode"),
      fanModeName:  byKeyOrPrefix("fan_mode_sensor",         "sensor", "fan_mode"),
    };

    const supplyTemp    = numVal(hass, sensorLookups.supplyTemp);
    const outdoorTemp   = numVal(hass, sensorLookups.outdoorTemp);
    const extractTemp   = numVal(hass, sensorLookups.extractTemp);
    const humidity      = numVal(hass, sensorLookups.humidity);
    const co2           = numVal(hass, sensorLookups.co2);
    const safSpeed      = numVal(hass, sensorLookups.safSpeed);
    const eafSpeed      = numVal(hass, sensorLookups.eafSpeed);
    const safRpm        = numVal(hass, sensorLookups.safRpm);
    const eafRpm        = numVal(hass, sensorLookups.eafRpm);
    const filterDays    = numVal(hass, sensorLookups.filterDays);
    const remainingMin  = numVal(hass, sensorLookups.remainingMin);
    const userModeName  = strVal(hass, sensorLookups.userModeName);
    const fanModeName   = strVal(hass, sensorLookups.fanModeName);

    // ECO switch
    const ecoEntityId = byKey["eco_mode"] ?? `switch.${p}_eco_mode`;
    const ecoState = hass.states[ecoEntityId];
    const ecoOn = ecoState?.state === "on";

    // Alarms
    const activeAlarms = [];
    if (cfg.show_alarms) {
      const alarmIds = alarmEntityIds.length
        ? alarmEntityIds
        : Object.keys(hass.states).filter(id => id.startsWith(`binary_sensor.${p}_alarm_`));
      alarmIds.forEach(eid => {
        const s = hass.states[eid];
        if (s?.state === "on") {
          const label = s.attributes.friendly_name
            ?.replace(/^.*?Alarm:\s*/i, "")
            ?? eid;
          activeAlarms.push(label);
        }
      });
    }

    // Functions
    const activeFunctions = [];
    if (cfg.show_functions) {
      const fnIds = fnEntityIds.length
        ? fnEntityIds
        : Object.keys(hass.states).filter(id => id.startsWith(`binary_sensor.${p}_function_`));
      fnIds.forEach(eid => {
        const s = hass.states[eid];
        if (s && s.state !== "unavailable" && s.state !== "unknown") {
          // Label: strip device name + "Function:" prefix added by _attr_has_entity_name
          const raw = s.attributes.friendly_name ?? eid;
          const label = raw.replace(/^.*?Function:\s*/i, "").replace(/^.*?funksjon:\s*/i, "");
          activeFunctions.push({ label, active: s.state === "on" });
        }
      });
    }


    return {
      climateState,
      currentTemp,
      targetTemp: this._spTemp ?? targetTemp,
      targetTempReal: targetTemp,
      hvacMode,
      hvacAction,
      fanMode,
      presetMode,
      availableFanModes,
      availablePresets,
      supplyTemp, outdoorTemp, extractTemp,
      humidity, co2,
      safSpeed, eafSpeed, safRpm, eafRpm,
      filterDays, remainingMin,
      userModeName, fanModeName,
      ecoOn,
      ecoEntityId,
      activeAlarms,
      activeFunctions,
    };
  }

  // ── Render ───────────────────────────────────────────────────────────────

  _render() {
    if (!this._config || !this._hass) return;
    const d = this._data();
    if (!d) return;

    if (!this._rendered) {
      this._buildDOM();
      this._rendered = true;
    }
    this._updateDOM(d);
  }

  _buildDOM() {
    const shadow = this.shadowRoot;
    shadow.innerHTML = `
      <style>${css}</style>
      <ha-card class="card">
        <div class="header" id="header">
          <div class="header-left">
            <svg class="header-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" fill="var(--sa-primary,#004a87)">
              <!-- Systemair spiral dot logo -->
              <!-- Large dots – outer arc (bottom-left) -->
              <circle cx="18" cy="72" r="8.5"/>
              <circle cx="10" cy="52" r="7.5"/>
              <circle cx="16" cy="32" r="7"/>
              <circle cx="30" cy="16" r="6.5"/>
              <circle cx="50" cy="9"  r="6"/>
              <!-- Medium dots – middle arc -->
              <circle cx="69" cy="14" r="5.2"/>
              <circle cx="83" cy="28" r="4.6"/>
              <circle cx="89" cy="46" r="4"/>
              <circle cx="86" cy="64" r="3.5"/>
              <!-- Inner arc (top-right, small dots) -->
              <circle cx="74" cy="78" r="3"/>
              <circle cx="58" cy="87" r="2.6"/>
              <circle cx="41" cy="88" r="2.2"/>
              <circle cx="26" cy="83" r="1.9"/>
              <!-- Inner spiral continuation -->
              <circle cx="36" cy="34" r="5.5"/>
              <circle cx="52" cy="26" r="5"/>
              <circle cx="67" cy="34" r="4.4"/>
              <circle cx="74" cy="49" r="3.8"/>
              <circle cx="70" cy="64" r="3.2"/>
              <circle cx="57" cy="72" r="2.8"/>
              <circle cx="43" cy="70" r="2.4"/>
              <circle cx="34" cy="60" r="2.1"/>
              <circle cx="33" cy="48" r="1.8"/>
              <!-- Core -->
              <circle cx="42" cy="43" r="4.2"/>
              <circle cx="52" cy="44" r="3.2"/>
              <circle cx="58" cy="53" r="2.6"/>
              <circle cx="50" cy="58" r="2"/>
            </svg>
            <div>
              <div class="header-title" id="header-title"></div>
              <div class="header-subtitle" id="header-subtitle"></div>
            </div>
          </div>
          <div class="header-right">
            <div class="alarm-badge" id="alarm-badge" style="display:none"></div>
            <ha-icon class="collapse-icon open" id="collapse-icon" icon="mdi:chevron-up"></ha-icon>
          </div>
        </div>

        <div class="body" id="body">

          <!-- Temperature Control -->
          <div class="section">
            <div class="section-label" id="sl-temp">
              <span>Temperature</span>
              <ha-icon class="chevron open" icon="mdi:chevron-up"></ha-icon>
            </div>
            <div class="section-content" id="sc-temp">
              <div class="temp-row">
                <div class="temp-display">
                  <div class="temp-current" id="temp-current">—<sup>°C</sup></div>
                  <div class="temp-label">Supply air</div>
                </div>
                <div class="temp-display">
                  <div class="temp-current" id="temp-outdoor" style="font-size:1.5rem;color:var(--sa-sub)">—<sup>°C</sup></div>
                  <div class="temp-label">Outdoor</div>
                </div>
                <div class="temp-setpoint">
                  <div class="temp-sp-label">Setpoint</div>
                  <div class="temp-sp-controls">
                    <button class="sp-btn" id="sp-down">−</button>
                    <div class="sp-value" id="sp-value">—</div>
                    <button class="sp-btn" id="sp-up">+</button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <hr class="divider">

          <!-- Fan Speed -->
          <div class="section">
            <div class="section-label" id="sl-fan">
              <span>Fan Speed</span>
              <ha-icon class="chevron open" icon="mdi:chevron-up"></ha-icon>
            </div>
            <div class="section-content" id="sc-fan">
              <div style="margin-bottom:6px">
                <div style="font-size:0.78rem; color:var(--sa-sub); margin-bottom:4px">Supply fan</div>
                <div class="fan-bar-row">
                  <div class="fan-bar-wrap">
                    <div class="fan-bar-bg">
                      <div class="fan-bar-fill" id="saf-bar" style="width:0%"></div>
                    </div>
                  </div>
                  <div class="fan-bar-val" id="saf-val">—</div>
                </div>
                <div id="saf-rpm" style="font-size:0.72rem; color:var(--sa-sub); margin-top:2px"></div>
              </div>
              <div>
                <div style="font-size:0.78rem; color:var(--sa-sub); margin-bottom:4px">Extract fan</div>
                <div class="fan-bar-row">
                  <div class="fan-bar-wrap">
                    <div class="fan-bar-bg">
                      <div class="fan-bar-fill" id="eaf-bar" style="width:0%"></div>
                    </div>
                  </div>
                  <div class="fan-bar-val" id="eaf-val">—</div>
                </div>
                <div id="eaf-rpm" style="font-size:0.72rem; color:var(--sa-sub); margin-top:2px"></div>
              </div>
              <div class="chips" id="fan-mode-chips" style="margin-top:10px"></div>
            </div>
          </div>

          <hr class="divider">

          <!-- Preset Modes -->
          <div class="section">
            <div class="section-label" id="sl-preset">
              <span>Preset / Mode</span>
              <ha-icon class="chevron open" icon="mdi:chevron-up"></ha-icon>
            </div>
            <div class="section-content" id="sc-preset">
              <div class="chips" id="preset-chips"></div>
            </div>
          </div>

          <hr class="divider">

          <!-- Air Quality -->
          <div class="section">
            <div class="section-label" id="sl-air">
              <span>Air Quality</span>
              <ha-icon class="chevron open" icon="mdi:chevron-up"></ha-icon>
            </div>
            <div class="section-content" id="sc-air">
              <div class="sensor-grid" id="sensor-grid"></div>
            </div>
          </div>

          <hr class="divider">

          <!-- Timed Modes -->
          <div class="section">
            <div class="section-label" id="sl-timed">
              <span>Timed Modes</span>
              <ha-icon class="chevron open" icon="mdi:chevron-up"></ha-icon>
            </div>
            <div class="section-content" id="sc-timed">
              <div class="timed-grid" id="timed-grid"></div>
            </div>
          </div>

          <hr class="divider">

          <!-- ECO Mode + Status -->
          <div class="section">
            <div class="section-label" id="sl-eco">
              <span>ECO Mode</span>
              <ha-icon class="chevron open" icon="mdi:chevron-up"></ha-icon>
            </div>
            <div class="section-content" id="sc-eco">
              <div class="eco-row">
                <div class="eco-toggle" id="eco-toggle">
                  <ha-icon icon="mdi:leaf" style="--mdc-icon-size:20px;color:var(--sa-green)"></ha-icon>
                  <span class="eco-label">ECO mode</span>
                </div>
                <div class="toggle-track" id="eco-track">
                  <div class="toggle-thumb"></div>
                </div>
              </div>
            </div>
          </div>

          <!-- Alarms -->
          <div class="section" id="section-alarms">
            <hr class="divider">
            <div class="section-label" id="sl-alarms">
              <span>Alarms</span>
              <ha-icon class="chevron open" icon="mdi:chevron-up"></ha-icon>
            </div>
            <div class="section-content" id="sc-alarms">
              <div class="alarm-list" id="alarm-list"></div>
            </div>
          </div>

          <!-- Active Functions -->
          <div class="section" id="section-functions">
            <hr class="divider">
            <div class="section-label" id="sl-functions">
              <span>Active Functions</span>
              <ha-icon class="chevron open" icon="mdi:chevron-up"></ha-icon>
            </div>
            <div class="section-content" id="sc-functions">
              <div class="function-chips" id="fn-chips"></div>
            </div>
          </div>

        </div>
      </ha-card>
    `;

    this._bindEvents();
  }

  _bindEvents() {
    const shadow = this.shadowRoot;

    // Header collapse
    shadow.getElementById("header").addEventListener("click", () => {
      const body = shadow.getElementById("body");
      const icon = shadow.getElementById("collapse-icon");
      const hidden = body.style.display === "none";
      body.style.display = hidden ? "" : "none";
      icon.classList.toggle("open", hidden);
    });

    // Section collapse helpers
    const sections = [
      ["sl-temp", "sc-temp"],
      ["sl-fan", "sc-fan"],
      ["sl-preset", "sc-preset"],
      ["sl-air", "sc-air"],
      ["sl-timed", "sc-timed"],
      ["sl-eco", "sc-eco"],
      ["sl-alarms", "sc-alarms"],
      ["sl-functions", "sc-functions"],
    ];
    sections.forEach(([labelId, contentId]) => {
      const label = shadow.getElementById(labelId);
      if (!label) return;
      label.addEventListener("click", () => {
        const content = shadow.getElementById(contentId);
        const chevron = label.querySelector(".chevron");
        const hidden = content.classList.toggle("hidden");
        chevron?.classList.toggle("open", !hidden);
      });
    });

    // Setpoint buttons
    shadow.getElementById("sp-down").addEventListener("click", () => this._changeSetpoint(-0.5));
    shadow.getElementById("sp-up").addEventListener("click", () => this._changeSetpoint(0.5));

    // ECO toggle
    const ecoToggle = shadow.getElementById("eco-toggle");
    const ecoTrack = shadow.getElementById("eco-track");
    [ecoToggle, ecoTrack].forEach(el => {
      el.addEventListener("click", () => this._toggleEco());
    });
  }

  // ── Update DOM ───────────────────────────────────────────────────────────

  _updateDOM(d) {
    const s = this.shadowRoot;
    const cfg = this._config;

    // Header
    s.getElementById("header-title").textContent = cfg.title;
    const subtitle = [
      d.hvacMode ? `Mode: ${d.hvacMode}` : null,
      d.hvacAction ? d.hvacAction : null,
    ].filter(Boolean).join(" · ");
    s.getElementById("header-subtitle").textContent = subtitle;

    const alarmBadge = s.getElementById("alarm-badge");
    if (d.activeAlarms.length > 0) {
      alarmBadge.style.display = "";
      alarmBadge.textContent = `⚠ ${d.activeAlarms.length}`;
    } else {
      alarmBadge.style.display = "none";
    }

    // Temperature
    const supplyDisplay = d.supplyTemp !== null ? d.supplyTemp : d.currentTemp;
    s.getElementById("temp-current").innerHTML = supplyDisplay !== null
      ? `${supplyDisplay.toFixed(1)}<sup>°C</sup>`
      : `—<sup>°C</sup>`;
    s.getElementById("temp-outdoor").innerHTML = d.outdoorTemp !== null
      ? `${d.outdoorTemp.toFixed(1)}<sup>°C</sup>`
      : `—<sup>°C</sup>`;
    s.getElementById("sp-value").textContent = d.targetTemp !== null
      ? `${d.targetTemp.toFixed(1)}°`
      : "—";

    // Fan bars
    const safPct = d.safSpeed ?? 0;
    const eafPct = d.eafSpeed ?? 0;
    s.getElementById("saf-bar").style.width = `${safPct}%`;
    s.getElementById("saf-val").textContent = d.safSpeed !== null ? `${safPct}%` : "—";
    s.getElementById("eaf-bar").style.width = `${eafPct}%`;
    s.getElementById("eaf-val").textContent = d.eafSpeed !== null ? `${eafPct}%` : "—";
    const safRpmEl = s.getElementById("saf-rpm");
    if (safRpmEl) safRpmEl.textContent = d.safRpm !== null ? `${Math.round(d.safRpm)} RPM` : "";
    const eafRpmEl = s.getElementById("eaf-rpm");
    if (eafRpmEl) eafRpmEl.textContent = d.eafRpm !== null ? `${Math.round(d.eafRpm)} RPM` : "";

    // Fan mode chips
    const fanChipsEl = s.getElementById("fan-mode-chips");
    fanChipsEl.innerHTML = "";
    const fanIcons = { low: "mdi:fan-speed-1", medium: "mdi:fan-speed-2", high: "mdi:fan-speed-3", normal: "mdi:fan-speed-2" };
    d.availableFanModes.forEach(mode => {
      const chip = document.createElement("div");
      chip.className = "chip" + (mode === d.fanMode ? " active" : "");
      chip.innerHTML = `<ha-icon icon="${fanIcons[mode] ?? "mdi:fan"}"></ha-icon> ${mode}`;
      chip.addEventListener("click", () => {
        this._hass.callService("climate", "set_fan_mode", {
          entity_id: cfg.entity,
          fan_mode: mode,
        });
      });
      fanChipsEl.appendChild(chip);
    });

    // Preset chips
    const presetIcons = {
      auto:      "mdi:autorenew",
      manual:    "mdi:hand-back-right",
      away:      "mdi:home-export-outline",
      boost:     "mdi:rocket-launch",
      comfort:   "mdi:sofa",
      fireplace: "mdi:fireplace",
      holiday:   "mdi:beach",
    };
    const presetChipsEl = s.getElementById("preset-chips");
    presetChipsEl.innerHTML = "";

    // Auto / Manual chips (derived from hvac_mode, not preset_modes)
    const hvacChips = [
      { label: "Auto",   mode: "auto",     service: "set_hvac_mode", serviceKey: "hvac_mode" },
      { label: "Manual", mode: "fan_only", service: "set_hvac_mode", serviceKey: "hvac_mode" },
    ];
    hvacChips.forEach(({ label, mode, service, serviceKey }) => {
      const isActive = d.presetMode === "none" && d.hvacMode === mode;
      const chip = document.createElement("div");
      chip.className = "chip" + (isActive ? " active" : "");
      chip.innerHTML = `<ha-icon icon="${presetIcons[label.toLowerCase()] ?? "mdi:cog"}"></ha-icon> ${label}`;
      chip.addEventListener("click", () => {
        this._hass.callService("climate", service, {
          entity_id: cfg.entity,
          [serviceKey]: mode,
        });
      });
      presetChipsEl.appendChild(chip);
    });

    // Timed preset chips (skip "none")
    d.availablePresets.filter(p => p !== "none").forEach(preset => {
      const chip = document.createElement("div");
      chip.className = "chip" + (preset === d.presetMode ? " active" : "");
      chip.innerHTML = `<ha-icon icon="${presetIcons[preset] ?? "mdi:cog"}"></ha-icon> ${preset}`;
      chip.addEventListener("click", () => {
        this._hass.callService("climate", "set_preset_mode", {
          entity_id: cfg.entity,
          preset_mode: preset,
        });
      });
      presetChipsEl.appendChild(chip);
    });

    // Sensor grid
    const sensorGrid = s.getElementById("sensor-grid");
    sensorGrid.innerHTML = "";
    const sensors = [
      { icon: "mdi:water-percent", val: d.humidity !== null ? `${d.humidity}%` : "—", label: "Humidity" },
      { icon: "mdi:molecule-co2", val: d.co2 !== null ? `${Math.round(d.co2)} ppm` : "—", label: "CO₂" },
      { icon: "mdi:thermometer-water", val: d.extractTemp !== null ? `${d.extractTemp.toFixed(1)}°C` : "—", label: "Extract" },
      { icon: "mdi:air-filter", val: d.filterDays !== null ? `${Math.round(d.filterDays)} d` : "—", label: "Filter left" },
    ];
    sensors.forEach(({ icon, val, label }) => {
      const tile = document.createElement("div");
      tile.className = "sensor-tile";
      tile.innerHTML = `<ha-icon class="sensor-icon" icon="${icon}"></ha-icon><div class="sensor-val">${val}</div><div class="sensor-lbl">${label}</div>`;
      sensorGrid.appendChild(tile);
    });

    // Timed modes
    const timedGrid = s.getElementById("timed-grid");
    timedGrid.innerHTML = "";
    const timedModes = [
      { preset: "away",      service: "set_away_mode",      icon: "mdi:home-export-outline", label: "Away",      duration: "8 h",    defaultVal: 8 },
      { preset: "comfort",   service: "set_crowded_mode",   icon: "mdi:account-group",       label: "Crowded",   duration: "4 h",    defaultVal: 4 },
      { preset: "boost",     service: "set_refresh_mode",   icon: "mdi:refresh",             label: "Refresh",   duration: "60 min", defaultVal: 60 },
      { preset: "fireplace", service: "set_fireplace_mode", icon: "mdi:fireplace",           label: "Fireplace", duration: "30 min", defaultVal: 30 },
      { preset: "holiday",   service: "set_holiday_mode",   icon: "mdi:beach",               label: "Holiday",   duration: "7 d",    defaultVal: 7 },
    ];
    timedModes.forEach(tm => {
      const isActive = d.presetMode === tm.preset;
      const btn = document.createElement("div");
      btn.className = "timed-btn" + (isActive ? " active" : "");
      btn.innerHTML = `
        <ha-icon icon="${tm.icon}"></ha-icon>
        <div class="timed-name">${tm.label}</div>
        <div class="timed-duration">${tm.duration}</div>
        ${isActive && d.remainingMin !== null ? `<div class="remaining-badge">${Math.round(d.remainingMin)} min left</div>` : ""}
      `;
      btn.addEventListener("click", () => {
        this._hass.callService("systemair", tm.service, {
          entity_id: this._config.entity,
          duration: tm.defaultVal,
        });
      });
      timedGrid.appendChild(btn);
    });

    // ECO
    const ecoTrack = s.getElementById("eco-track");
    if (d.ecoOn) {
      ecoTrack.classList.add("on");
    } else {
      ecoTrack.classList.remove("on");
    }

    // Alarms section visibility
    const sectionAlarms = s.getElementById("section-alarms");
    if (!cfg.show_alarms) {
      sectionAlarms.style.display = "none";
    } else {
      sectionAlarms.style.display = "";
      const alarmList = s.getElementById("alarm-list");
      alarmList.innerHTML = "";
      if (d.activeAlarms.length === 0) {
        alarmList.innerHTML = `<div class="alarm-none">No active alarms</div>`;
      } else {
        d.activeAlarms.forEach(label => {
          const item = document.createElement("div");
          item.className = "alarm-item";
          item.innerHTML = `<ha-icon icon="mdi:alert-circle"></ha-icon><span>${label}</span>`;
          alarmList.appendChild(item);
        });
      }
    }

    // Functions section
    const sectionFunctions = s.getElementById("section-functions");
    if (!cfg.show_functions) {
      sectionFunctions.style.display = "none";
    } else {
      sectionFunctions.style.display = "";
      const fnChips = s.getElementById("fn-chips");
      fnChips.innerHTML = "";
      const fnIcons = {
        cooling: "mdi:snowflake",
        heating: "mdi:radiator",
        "heat recovery": "mdi:recycle",
        defrosting: "mdi:snowflake-melt",
        "eco mode active": "mdi:leaf",
        "pressure guard": "mdi:gauge",
        "moisture transfer": "mdi:water-sync",
        "secondary air": "mdi:air-purifier",
        "free cooling": "mdi:fan",
        "cooling recovery": "mdi:snowflake-check",
        "user lock": "mdi:lock",
      };
      d.activeFunctions.forEach(({ label, active }) => {
        const chip = document.createElement("div");
        chip.className = "fn-chip" + (active ? " active" : "");
        const iconName = fnIcons[label.toLowerCase()] ?? "mdi:circle-small";
        chip.innerHTML = `<ha-icon icon="${iconName}"></ha-icon> ${label}`;
        fnChips.appendChild(chip);
      });
    }
  }

  // ── Actions ──────────────────────────────────────────────────────────────

  _changeSetpoint(delta) {
    const d = this._data();
    if (!d || d.targetTempReal === null) return;
    const next = Math.round((d.targetTempReal + delta) * 2) / 2;
    const clamped = Math.min(30, Math.max(12, next));
    this._spTemp = clamped;
    this._render();
    clearTimeout(this._spTimer);
    this._spTimer = setTimeout(() => {
      this._hass.callService("climate", "set_temperature", {
        entity_id: this._config.entity,
        temperature: clamped,
      });
      this._spTemp = null;
    }, 800);
  }

  _toggleEco() {
    const d = this._data();
    if (!d) return;
    if (!this._hass.states[d.ecoEntityId]) return;
    this._hass.callService("switch", d.ecoOn ? "turn_off" : "turn_on", {
      entity_id: d.ecoEntityId,
    });
  }

  // ── Card sizing ──────────────────────────────────────────────────────────

  getCardSize() { return 8; }
}

customElements.define("systemair-card", SystemairCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "systemair-card",
  name: "Systemair HVAC Card",
  description: "Compact control card for the Systemair cloud integration",
  preview: false,
  documentationURL: "https://github.com/sirkro/hass-systemair-hvac",
});

console.info(
  `%c SYSTEMAIR-CARD %c v${CARD_VERSION} `,
  "background:#1976d2;color:#fff;padding:2px 6px;border-radius:3px 0 0 3px;font-weight:700",
  "background:#333;color:#fff;padding:2px 6px;border-radius:0 3px 3px 0"
);
