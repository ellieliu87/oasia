"""
Oasia — Magnifi-style theme (CSS only).

CSS is derived from the provided magnifi layout code with Gradio reset
overrides and tab-switching support added.
"""
import gradio as gr


CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --navy:       #0F1F3D;
  --navy-mid:   #1A3060;
  --blue:       #3B6FD4;
  --blue-light: #EEF3FF;
  --emerald:    #059669;
  --emerald-bg: #ECFDF5;
  --coral:      #E5484D;
  --coral-bg:   #FFF1F2;
  --amber:      #D97706;
  --amber-bg:   #FFFBEB;
  --border:     #E2E8F0;
  --border-dark:#CBD5E1;
  --bg:         #F8F9FC;
  --surface:    #FFFFFF;
  --text:       #0F172A;
  --text-2:     #334155;
  --text-3:     #64748B;
  --text-4:     #94A3B8;
  --shadow-sm:  0 1px 3px rgba(15,31,61,0.06), 0 1px 2px rgba(15,31,61,0.04);
  --shadow:     0 4px 16px rgba(15,31,61,0.08), 0 1px 4px rgba(15,31,61,0.04);
  --shadow-lg:  0 12px 40px rgba(15,31,61,0.12), 0 4px 12px rgba(15,31,61,0.06);
  --radius:     14px;
  --serif:      'DM Serif Display', Georgia, serif;
  --sans:       'DM Sans', system-ui, sans-serif;
  --mono:       'JetBrains Mono', monospace;
}

/* ── GRADIO RESETS ── */
body, .gradio-container { background: var(--bg) !important; font-family: var(--sans) !important; color: var(--text) !important; overflow-x: hidden !important; }
.gradio-container { max-width: 100% !important; padding: 0 !important; margin: 0 !important; overflow-x: hidden !important; }
.gradio-container > .main, .gradio-container > .main > .wrap { padding: 0 !important; gap: 0 !important; max-width: 100% !important; overflow-x: hidden !important; }
footer, .gradio-footer { display: none !important; }
.contain { max-width: 100% !important; }
.gap { gap: 0 !important; }

/* ── HIDDEN MARKET PILLS SOURCE (synced to topbar by JS) ── */
#nexus-market-hidden-col { display: none !important; }

/* ── TOPBAR ── */
#nexus-topbar {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 24px;
  gap: 20px;
  box-shadow: var(--shadow-sm);
  height: 60px;
  min-height: 60px;
}

.logo {
  font-family: var(--serif);
  font-size: 22px;
  color: var(--navy);
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

.logo-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--blue), var(--emerald));
  display: inline-block;
  flex-shrink: 0;
}

.topbar-search {
  flex: 1; max-width: 400px; position: relative;
}
.topbar-search input {
  width: 100%;
  padding: 8px 14px 8px 34px;
  background: #F1F5F9;
  border: 1.5px solid transparent;
  border-radius: 10px;
  font-family: var(--sans);
  font-size: 13px;
  color: var(--text);
  outline: none;
  transition: all 0.2s;
}
.topbar-search input:focus { background: var(--surface); border-color: var(--blue); box-shadow: 0 0 0 3px rgba(59,111,212,0.1); }
.topbar-search svg { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); color: #94A3B8; }

.topbar-right { margin-left: auto; display: flex; align-items: center; gap: 12px; flex-shrink: 0; }

#nexus-topbar-market { display: flex !important; align-items: center !important; gap: 8px !important; flex-shrink: 0 !important; flex-wrap: nowrap !important; }

.market-pill {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 20px;
  font-size: 12px;
  font-family: var(--mono);
  white-space: nowrap;
  line-height: 1;
  vertical-align: middle;
  flex-shrink: 0;
}
.pill-label { color: var(--text-4); font-family: var(--sans); font-size: 11px; }
.pill-val   { color: var(--text); font-weight: 500; }
.pill-chg-up { color: var(--emerald); font-size: 11px; }
.pill-chg-dn { color: var(--coral);   font-size: 11px; }

.avatar {
  width: 34px; height: 34px; border-radius: 50%;
  background: linear-gradient(135deg, var(--navy), var(--blue));
  color: white; font-size: 13px; font-weight: 600;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; flex-shrink: 0;
  user-select: none;
}

.avatar-wrap {
  position: relative;
  flex-shrink: 0;
}

/* Allow the dropdown to extend below the topbar — Gradio's .block wrapper
   defaults to overflow:hidden which clips position:absolute children. */
.block:has(#nexus-topbar),
.block:has(#nexus-topbar) > *,
#nexus-topbar {
  overflow: visible !important;
}

.avatar-menu {
  display: none;
  position: absolute;
  top: 100%;
  right: 0;
  width: 200px;
  background: var(--surface);
  border: 1px solid var(--border-dark);
  border-radius: 12px;
  box-shadow: var(--shadow-lg);
  z-index: 2000;
  overflow: hidden;
}
.avatar-menu.open { display: block; }
.avatar-wrap:hover .avatar-menu { display: block; }

.avatar-menu-header {
  padding: 14px 16px 12px;
}
.avatar-menu-divider {
  height: 1px;
  background: var(--border);
  margin: 0;
}
.avatar-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 16px;
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 500;
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
  color: var(--text-2);
  transition: background 0.15s, color 0.15s;
}
.avatar-menu-item:hover { background: var(--bg); }
.avatar-menu-logout:hover { color: var(--coral); background: var(--coral-bg); }

/* ── Bottom-align mixed label+input / button rows ── */
#sa-search-row,
#pp-resume-row {
  align-items: flex-end !important;
}

/* ── Global: flatten all Gradio blocks in every tab ──
   div.block   = gr.Column / gr.Group wrappers
   label.block = form input containers (textbox, number, dropdown…)
   .form       = gr.Group wrapper
   .card (dashboard HTML) → untouched (different class / different DOM path) */
#nexus-main-tabs .tabitem div.block,
#nexus-main-tabs .tabitem label.block,
#nexus-main-tabs .tabitem .form {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}

/* ── Plain section — no card border or background ── */
.nexus-plain-section {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
}
.nexus-plain-section > .gap,
.nexus-plain-section > div {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
}
/* Strip the padding Gradio adds around individual gr.HTML blocks inside the section */
.nexus-plain-html,
.nexus-plain-html > * {
  padding: 0 !important;
  margin: 0 !important;
  background: transparent !important;
  border: none !important;
}

/* ── BODY ROW ── */
#nexus-body-row {
  height: calc(100vh - 60px);
  overflow: hidden;
  display: flex !important;
  flex-wrap: nowrap !important;
  gap: 0 !important;
  /* No transform/filter: must not trap position:fixed listboxes */
  transform: none !important;
  filter: none !important;
  contain: none !important;
}

/* Strip Gradio chrome from body row children */
#nexus-body-row > * {
  padding: 0 !important;
  margin: 0 !important;
  gap: 0 !important;
  min-height: 0 !important;
  max-height: 100% !important;
}

/* ── SIDEBAR ── */
#nexus-sidebar-col {
  background: var(--surface) !important;
  border-right: 1px solid var(--border) !important;
  height: 100% !important;
  overflow-y: auto !important;
  display: flex !important;
  flex-direction: column !important;
  flex-shrink: 0 !important;
  padding: 12px 0 0 !important;
}

/* Strip extra blocks inside sidebar */
#nexus-sidebar-col > .block,
#nexus-sidebar-col .block { border: none !important; box-shadow: none !important; background: transparent !important; padding: 0 !important; }

.nav-section { margin-bottom: 24px; }

.nav-label {
  padding: 0 18px 6px;
  font-size: 10px; font-weight: 600;
  letter-spacing: 0.1em; color: var(--text-4);
  text-transform: uppercase; font-family: var(--sans);
}

.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 18px;
  cursor: pointer;
  color: var(--text-3); font-size: 13.5px; font-weight: 500;
  border-left: 2px solid transparent;
  transition: all 0.15s;
  margin-right: 8px; border-radius: 0 8px 8px 0;
  font-family: var(--sans);
  user-select: none;
}
.nav-item:hover { color: var(--text); background: var(--bg); }
.nav-item.active { color: var(--blue); background: var(--blue-light); border-left-color: var(--blue); font-weight: 600; }
.nav-icon { font-size: 16px; width: 20px; text-align: center; flex-shrink: 0; }

.nav-badge {
  margin-left: auto;
  background: var(--blue-light); color: var(--blue);
  font-size: 10px; font-weight: 700;
  padding: 2px 6px; border-radius: 10px;
}

.sidebar-footer { margin-top: auto; padding: 16px 18px; border-top: 1px solid var(--border); }
.user-card { display: flex; align-items: center; gap: 10px; }
.user-name { font-size: 13px; font-weight: 600; color: var(--text); font-family: var(--sans); }
.user-role { font-size: 11px; color: var(--text-4); font-family: var(--sans); }

/* ── MAIN TABS AREA ── */
#nexus-main-col {
  height: 100% !important;
  overflow: hidden !important;
  display: flex !important;
  flex-direction: column !important;
  background: var(--bg) !important;
  flex: 1 !important;
  min-width: 0 !important;
  /* No transform/filter: must not trap position:fixed listboxes */
  transform: none !important;
  filter: none !important;
  contain: none !important;
}

#nexus-main-col > .block { border: none !important; box-shadow: none !important; background: transparent !important; padding: 0 !important; height: 100% !important; }

/* Hide the Gradio tab nav — collapse to zero height so JS click() still works */
/* NOTE: do NOT use display:none or visibility:hidden — JS needs to click the buttons */
#nexus-main-tabs .tab-nav,
#nexus-main-tabs > div > .tab-nav,
#nexus-main-tabs > .tabs > .tab-nav,
#nexus-main-tabs [role="tablist"],
div#nexus-main-tabs > div > [role="tablist"],
#nexus-main-tabs > div:first-child > *:first-child:has(button[role="tab"]) {
  height: 0 !important;
  min-height: 0 !important;
  max-height: 0 !important;
  overflow: hidden !important;
  padding: 0 !important;
  margin: 0 !important;
  border: none !important;
  flex-shrink: 0 !important;
  opacity: 0 !important;
  pointer-events: none !important;
}

#nexus-main-tabs {
  height: 100% !important;
  display: flex !important;
  flex-direction: column !important;
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
}

#nexus-main-tabs .tabitem {
  overflow-y: auto !important;
  overflow-x: clip !important;   /* clip (not hidden) so position:sticky still works */
  padding: 0 !important;
  border: none !important;
  background: var(--bg) !important;
  flex: 1 !important;
  min-width: 0 !important;
  /* IMPORTANT: no transform/filter/perspective here — those would create a new
     containing block for position:fixed and trap dropdown listboxes inside */
  transform: none !important;
  filter: none !important;
  contain: none !important;
}

/* Main scrollable content inside tabs */
.nexus-tab-content {
  padding: 28px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 100%;
  box-sizing: border-box;
  max-width: 100%;
  overflow-x: hidden;
}

/* ── DASHBOARD HEADER ROW ── */
/* sticky so it stays at the top while content scrolls — this keeps the
   dropdown anchor fixed in the viewport, so the position:fixed listbox
   always appears in the right place regardless of scroll position. */
#nexus-dash-header-row {
  position: sticky !important;
  top: 0 !important;
  z-index: 200 !important;
  background: var(--bg) !important;
  border: none !important;
  border-bottom: 1px solid var(--border) !important;
  padding: 10px 28px 10px !important;
  align-items: center !important;
  flex-wrap: nowrap !important;
  flex-shrink: 0 !important;
  gap: 0 !important;
}
/* Strip all Gradio chrome from every child */
#nexus-dash-header-row > *,
#nexus-dash-header-row .block,
#nexus-dash-header-row .wrap {
  padding: 0 !important; border: none !important;
  box-shadow: none !important; background: transparent !important;
  gap: 0 !important;
}

/* Title + subtitle */
.dash-header-left { display: flex; flex-direction: column; gap: 4px; }
.dash-header-title {
  font-family: var(--serif); font-size: 24px;
  color: var(--navy); line-height: 1.2;
}
.dash-header-sub {
  font-family: var(--sans); font-size: 12px;
  color: var(--text-3); letter-spacing: 0.01em;
}

/* Right-side controls — flush right, vertically centered */
#nexus-dash-header-right {
  display: flex !important; justify-content: flex-end !important;
  align-items: center !important;
}
#nexus-dash-header-right > *,
#nexus-dash-header-right .block,
#nexus-dash-header-right .wrap,
#nexus-dash-header-right label {
  padding: 0 !important; border: none !important;
  box-shadow: none !important; background: transparent !important;
  margin: 0 !important;
}
.dash-ctrl-row {
  display: flex !important; align-items: center !important;
  gap: 8px !important; flex-wrap: nowrap !important;
  justify-content: flex-end !important;
}
/* ── Override Gradio's default purple primary → our blue ── */
.gradio-container {
  --primary-50:  #EEF3FF !important;
  --primary-100: #E0EAFF !important;
  --primary-200: #C7D7FD !important;
  --primary-300: #A4BCFD !important;
  --primary-400: #6080E8 !important;
  --primary-500: #3B6FD4 !important;
  --primary-600: #1D4ED8 !important;
  --primary-700: #1A3060 !important;
  --primary-800: #0F1F3D !important;
  --primary-900: #0C1829 !important;
}

/* ── View run date dropdown (container=False → no outer block) ── */
#nexus-run-date-dd {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
}
#nexus-run-date-dd .wrap,
#nexus-run-date-dd .wrap-inner {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  min-height: unset !important;
  height: 34px !important;
}
#nexus-run-date-dd input {
  background: transparent !important;
  border: 1.5px solid var(--border-dark) !important;
  border-radius: 20px !important;
  font-size: 12px !important; font-weight: 600 !important;
  color: var(--text-2) !important;
  height: 34px !important; min-height: 34px !important;
  padding: 0 32px 0 14px !important;
  cursor: pointer !important;
  box-shadow: none !important; outline: none !important;
}
#nexus-run-date-dd input:focus { border-color: var(--blue) !important; background: transparent !important; box-shadow: none !important; }
/* Chevron button inside dropdown */
#nexus-run-date-dd button { background: transparent !important; border: none !important; box-shadow: none !important; }

/* Ctrl row alignment */
.dash-ctrl-row { align-items: center !important; }
.dash-ctrl-row > * { flex-shrink: 0 !important; }
.dash-ctrl-row .block { background: transparent !important; border: none !important; padding: 0 !important; box-shadow: none !important; }

/* Schedule toggle button — pill style */
#nexus-sched-toggle-btn button {
  font-size: 12px !important; font-weight: 600 !important;
  white-space: nowrap !important; letter-spacing: 0.01em !important;
  padding: 6px 14px !important; border-radius: 20px !important;
  border: 1.5px solid var(--border-dark) !important;
  background: var(--surface) !important; color: var(--text-2) !important;
}
#nexus-sched-toggle-btn button:hover {
  background: var(--blue-light) !important; border-color: var(--blue) !important;
  color: var(--blue) !important;
}

/* ── SCHEDULE POPUP (fixed modal) ── */
#nexus-sched-backdrop {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(15, 31, 61, 0.4);
  z-index: 1998;
}

/* Popup hidden by default; JS adds 'sched-open' class to show it instantly
   (no Gradio server round-trip = no blink). */
#nexus-sched-popup {
  display: none;
  position: fixed !important;
  top: 50% !important;
  left: 50% !important;
  transform: translate(-50%, -50%) !important;
  z-index: 1999 !important;
  width: 580px !important;
  max-width: calc(100vw - 48px) !important;
  background: var(--surface) !important;
  border: 1px solid var(--border-dark) !important;
  border-radius: 16px !important;
  box-shadow: var(--shadow-lg) !important;
  padding: 0 !important;
  margin: 0 !important;
  overflow: visible !important;
}
#nexus-sched-popup.sched-open {
  display: block !important;
}

/* Strip Gradio chrome on wrappers inside the popup */
#nexus-sched-popup > *,
#nexus-sched-popup .block,
#nexus-sched-popup .form {
  border: none !important;
  box-shadow: none !important;
  background: var(--surface) !important;
}

/* ── Popup header ── */
.sched-popup-hdr {
  display: flex !important;
  align-items: center !important;
  padding: 18px 22px 16px !important;
  border-bottom: 1px solid var(--border) !important;
  gap: 12px !important;
  flex-wrap: nowrap !important;
  background: var(--surface) !important;
}
.sched-popup-hdr > *,
.sched-popup-hdr .block,
.sched-popup-hdr .wrap {
  padding: 0 !important; border: none !important;
  box-shadow: none !important; background: transparent !important;
  margin: 0 !important;
}
.sched-popup-title {
  flex: 1;
  font-family: var(--sans); font-size: 15px; font-weight: 700;
  color: var(--navy); letter-spacing: 0.01em;
}

/* Close button */
#nexus-sched-close-btn { flex-shrink: 0 !important; }
#nexus-sched-close-btn button {
  width: 30px !important; height: 30px !important;
  padding: 0 !important; min-width: unset !important;
  border-radius: 8px !important; font-size: 16px !important;
  line-height: 1 !important; color: var(--text-3) !important;
  border: 1px solid var(--border) !important;
  background: var(--bg) !important; box-shadow: none !important;
}
#nexus-sched-close-btn button:hover {
  background: var(--border) !important; color: var(--text) !important;
  border-color: var(--border-dark) !important;
}

/* ── Frequency radio → styled as horizontal segmented control ── */
.sched-freq-col {
  padding: 20px 22px 0 !important;
  background: var(--surface) !important;
  border: none !important; box-shadow: none !important;
}
.sched-freq-col > *,
.sched-freq-col .block,
.sched-freq-col .wrap {
  border: none !important; box-shadow: none !important;
  background: transparent !important; padding: 0 !important;
}
/* Section label */
#nexus-sched-freq > label,
#nexus-sched-freq .block > label {
  display: block !important;
  font-size: 11px !important; font-weight: 600 !important;
  color: var(--text-3) !important; text-transform: uppercase !important;
  letter-spacing: .07em !important; margin-bottom: 8px !important;
}
/* Radio items row */
#nexus-sched-freq .wrap { display: flex !important; flex-direction: row !important; gap: 0 !important; padding: 0 !important; }
/* Hide the native radio circle */
#nexus-sched-freq input[type="radio"] { display: none !important; }
/* Each label = one segment */
#nexus-sched-freq .wrap > label,
#nexus-sched-freq span[data-testid="radio-label"],
#nexus-sched-freq label.svelte-1mdhmn6 {
  flex: 1 !important; text-align: center !important;
  padding: 8px 16px !important; cursor: pointer !important;
  background: var(--bg) !important;
  border: 1.5px solid var(--border-dark) !important;
  color: var(--text-2) !important;
  font-family: var(--sans) !important; font-size: 13px !important; font-weight: 500 !important;
  transition: all 0.15s !important;
  border-radius: 0 !important; margin: 0 !important;
  text-transform: none !important; letter-spacing: 0 !important;
}
#nexus-sched-freq .wrap > label:first-of-type { border-radius: 8px 0 0 8px !important; }
#nexus-sched-freq .wrap > label:last-of-type  { border-radius: 0 8px 8px 0 !important; border-left: none !important; }
#nexus-sched-freq .wrap > label:not(:first-of-type):not(:last-of-type) { border-left: none !important; }
#nexus-sched-freq .wrap > label:hover { background: var(--blue-light) !important; color: var(--blue) !important; }
/* Selected: input:checked + label */
#nexus-sched-freq input[type="radio"]:checked + label,
#nexus-sched-freq .wrap > label:has(input:checked) {
  background: var(--navy) !important; color: white !important;
  border-color: var(--navy) !important;
}

/* ── Time + day pickers row ── */
.sched-inputs-row {
  gap: 12px !important; align-items: flex-end !important;
  flex-wrap: wrap !important; padding: 14px 22px 0 !important;
  background: var(--surface) !important;
}
/* Clean up block chrome in inputs row */
.sched-inputs-row .block,
.sched-inputs-row .wrap {
  border: none !important; box-shadow: none !important;
  background: transparent !important;
}
/* Day-of-week dropdown (container=False): same style as a clean input */
.sched-inputs-row input,
.sched-inputs-row [role="combobox"] {
  background: var(--bg) !important;
  border: 1.5px solid var(--border-dark) !important;
  border-radius: 8px !important;
  color: var(--text) !important;
  box-shadow: none !important;
}
.sched-inputs-row input:focus,
.sched-inputs-row [role="combobox"]:focus {
  border-color: var(--blue) !important;
  background: var(--surface) !important;
  box-shadow: 0 0 0 3px rgba(59,111,212,0.1) !important;
  outline: none !important;
}

/* ── Action buttons row ── */
.sched-action-row {
  gap: 10px !important; padding: 16px 22px 20px !important;
  background: var(--surface) !important;
}

/* ── Status card inside popup ── */
#nexus-schedule-status { padding: 0 22px 20px !important; flex-shrink: 0 !important; background: var(--surface) !important; }

/* ── Dropdown listbox cosmetic theming ── */
/* Gradio 6.x handles all positioning/sizing for [role="listbox"] internally
   via position:fixed and its own JS (calculate_window_distance).
   We only add cosmetic overrides here — do NOT set position, z-index,
   max-height, overflow-y, or overflow-x as those conflict with Gradio. */
[role="option"] { background: transparent !important; color: var(--text) !important; font-size: 13px !important; cursor: pointer !important; }
[role="option"]:hover, [role="option"][aria-selected="true"] { background: var(--blue-light) !important; color: var(--blue) !important; }

.sched-status-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 4px;
}
.sched-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
}
.sched-title {
  font-family: var(--sans); font-size: 11px; font-weight: 600;
  color: var(--text-3); text-transform: uppercase; letter-spacing: 0.07em;
}
.sched-body { padding: 8px 14px; display: flex; flex-direction: column; gap: 5px; }
.sched-row  { display: flex; align-items: baseline; gap: 8px; }
.sched-label {
  font-family: var(--sans); font-size: 12px; color: var(--text-4);
  min-width: 130px; flex-shrink: 0;
}
.sched-val { font-family: var(--mono); font-size: 12px; color: var(--text); }
.sched-divider { border: none; border-top: 1px solid var(--border); margin: 4px 0; }

/* Spinner for running state */
.sched-spinner {
  display: inline-block; width: 9px; height: 9px;
  border: 2px solid #3B6FD4; border-top-color: transparent;
  border-radius: 50%; animation: sched-spin 0.7s linear infinite;
  margin-right: 6px; vertical-align: middle;
}
@keyframes sched-spin { to { transform: rotate(360deg); } }

/* Progress bar */
.sched-progress-wrap { padding: 4px 0 6px; }
.sched-progress-bar {
  height: 6px; background: var(--border); border-radius: 4px; overflow: hidden; margin-bottom: 5px;
}
.sched-progress-fill {
  height: 100%; background: var(--blue);
  border-radius: 4px; transition: width 0.4s ease;
}
.sched-progress-label {
  font-family: var(--mono); font-size: 11px; color: var(--text-3);
}

/* ── FAB BUTTON ── */
#nexus-agent-fab {
  position: fixed;
  bottom: 28px;
  right: 28px;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--navy), var(--blue));
  color: white;
  font-size: 22px;
  border: none;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(15,31,61,0.28), 0 2px 8px rgba(59,111,212,0.3);
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s, box-shadow 0.2s;
  line-height: 1;
}
#nexus-agent-fab:hover {
  transform: scale(1.08);
  box-shadow: 0 12px 32px rgba(15,31,61,0.32), 0 4px 12px rgba(59,111,212,0.4);
}
#nexus-agent-fab:active { transform: scale(0.96); }

/* ── AGENT POPUP ── */
#nexus-agent-popup {
  position: fixed;
  bottom: 96px;
  right: 28px;
  width: 460px;
  height: 580px;
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  z-index: 1100;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  /* hidden state */
  opacity: 0;
  transform: translateY(18px) scale(0.97);
  pointer-events: none;
  transition: opacity 0.22s ease, transform 0.22s ease;
}
#nexus-agent-popup.open {
  opacity: 1;
  transform: translateY(0) scale(1);
  pointer-events: all;
}

/* Gradio components inside the popup mount */
#nexus-agent-chat-mount { flex: 1 1 0; display: flex; flex-direction: column; overflow: hidden; min-height: 0; }

/* Popup close button hover */
#nexus-popup-close:hover { background: rgba(255,255,255,0.25) !important; }

/* ── POPUP RESIZE HANDLES ── */
/* Left-edge handle — drag left/right to change width */
#nexus-resize-left {
  position: absolute;
  top: 0; left: 0; bottom: 0;
  width: 6px;
  cursor: ew-resize;
  z-index: 10;
  border-radius: var(--radius) 0 0 var(--radius);
  background: transparent;
  transition: background 0.15s;
}
#nexus-resize-left:hover,
#nexus-resize-left.dragging { background: rgba(59,111,212,0.25); }

/* Top-edge handle — drag up/down to change height */
#nexus-resize-top {
  position: absolute;
  top: 0; left: 6px; right: 0;
  height: 6px;
  cursor: ns-resize;
  z-index: 10;
  border-radius: 0 var(--radius) 0 0;
  background: transparent;
  transition: background 0.15s;
}
#nexus-resize-top:hover,
#nexus-resize-top.dragging { background: rgba(59,111,212,0.25); }

/* Corner handle (top-left) — drag diagonally */
#nexus-resize-corner {
  position: absolute;
  top: 0; left: 0;
  width: 16px; height: 16px;
  cursor: nw-resize;
  z-index: 11;
  border-radius: var(--radius) 0 0 0;
  background: transparent;
}
/* grip dots visible on hover */
#nexus-resize-corner::before,
#nexus-resize-corner::after {
  content: '';
  position: absolute;
  border-radius: 1px;
  background: rgba(59,111,212,0.5);
  transition: background 0.15s;
}
#nexus-resize-corner::before {
  top: 4px; left: 4px;
  width: 6px; height: 2px;
  box-shadow: 0 3px 0 rgba(59,111,212,0.5);
}
#nexus-resize-corner::after {
  top: 4px; left: 4px;
  width: 2px; height: 6px;
  box-shadow: 3px 0 0 rgba(59,111,212,0.5);
}
#nexus-resize-corner:hover::before,
#nexus-resize-corner:hover::after { background: var(--blue); }
#nexus-resize-corner.dragging::before,
#nexus-resize-corner.dragging::after { background: var(--blue); }

/* ── AGENT STAGING (off-screen) ── */
#nexus-agent-staging {
  position: fixed !important;
  top: -9999px !important;
  left: -9999px !important;
  width: 460px !important;
  overflow: hidden !important;
}

#nexus-agent-popup .chat-header {
  background: linear-gradient(135deg, var(--navy) 0%, var(--navy-mid) 100%);
  padding: 16px 20px;
  display: flex; align-items: center; gap: 12px;
  flex-shrink: 0;
}
#nexus-agent-popup .chat-avatar { width:36px; height:36px; border-radius:50%; background: rgba(255,255,255,0.15); display:flex; align-items:center; justify-content:center; font-size:16px; flex-shrink:0; }
#nexus-agent-popup .chat-name { font-size:14px; font-weight:700; color: white !important; font-family: var(--sans); }
#nexus-agent-popup .chat-status { font-size:11px; color: rgba(255,255,255,0.65); display:flex; align-items:center; gap:5px; font-family: var(--sans); margin-top:2px; }
.live-dot { width:6px; height:6px; border-radius:50%; background:#4ade80; animation: livepulse 2s infinite; display:inline-block; }
@keyframes livepulse { 0%,100%{opacity:1} 50%{opacity:.4} }


/* ── CHAT MOUNT layout ── */
/* :has() selects every ancestor wrapper between mount and chatbot,          */
/* regardless of Gradio/Svelte auto-generated class names.                   */
#nexus-agent-chat-mount *:has(#nexus-chatbot) {
  flex: 1 1 0 !important;
  display: flex !important;
  flex-direction: column !important;
  min-height: 0 !important;
  overflow: hidden !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
  gap: 0 !important;
}

/* Chatbot fills all remaining height */
#nexus-chatbot {
  flex: 1 1 0 !important;
  height: auto !important;
  min-height: 0 !important;
  border: none !important;
  border-radius: 0 !important;
  background: var(--bg) !important;
  box-shadow: none !important;
  overflow: hidden !important;
}
#nexus-chatbot .bubble-wrap { padding: 10px 14px !important; gap: 8px !important; }

/* Hide Gradio progress / loading / pending indicators */
#nexus-agent-chat-mount .generating,
#nexus-agent-chat-mount .pending,
#nexus-agent-chat-mount .progress-bar,
#nexus-agent-chat-mount .eta-bar,
#nexus-agent-chat-mount .status-bar,
#nexus-agent-chat-mount .loader,
#nexus-agent-chat-mount [class*="progress"],
#nexus-agent-chat-mount [class*="status"] { display: none !important; }

/* ── INPUT BAR — pinned at the very bottom of the popup ─────────────────── */
#nexus-input-bar {
  flex-shrink: 0 !important;
  display: flex !important;
  align-items: center !important;
  gap: 6px !important;
  padding: 8px 12px 10px !important;
  background: var(--surface) !important;
  border-top: 1px solid var(--border) !important;
}
/* Strip box chrome from all Gradio wrappers inside the input bar */
#nexus-input-bar > *,
#nexus-input-bar .block,
#nexus-input-bar .wrap,
#nexus-input-bar label {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  padding: 0 !important;
  margin: 0 !important;
}
/* The textarea itself keeps a subtle border */
#nexus-msg-input textarea {
  background: #F1F5F9 !important;
  border: 1.5px solid var(--border-dark) !important;
  border-radius: 10px !important;
  font-family: var(--sans) !important;
  font-size: 13px !important;
  color: var(--text) !important;
  resize: none !important;
  padding: 6px 12px !important;
  min-height: 34px !important;
  max-height: 34px !important;
  line-height: 1.4 !important;
  transition: border-color 0.2s !important;
  box-shadow: none !important;
}
#nexus-msg-input textarea:focus {
  background: var(--surface) !important;
  border-color: var(--blue) !important;
  box-shadow: 0 0 0 3px rgba(59,111,212,0.1) !important;
  outline: none !important;
}

#nexus-send-btn {
  background: var(--navy) !important;
  border: none !important;
  border-radius: 10px !important;
  color: white !important;
  min-width: 36px !important;
  max-width: 36px !important;
  height: 34px !important;
  font-size: 15px !important;
  flex-shrink: 0 !important;
  padding: 0 !important;
}
#nexus-send-btn:hover { background: var(--navy-mid) !important; }

#nexus-clear-btn {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  color: var(--text-4) !important;
  font-size: 12px !important;
  flex-shrink: 0 !important;
  min-width: 28px !important;
  max-width: 28px !important;
  height: 34px !important;
  padding: 0 !important;
  border-radius: 8px !important;
}
#nexus-clear-btn:hover { color: var(--coral) !important; background: var(--coral-bg) !important; }

/* ── PAGE HEADER ── */
.page-header { display:flex; align-items:flex-end; justify-content:space-between; margin-bottom: 4px; }
.page-title  { font-family: var(--serif); font-size: 28px; color: var(--navy); line-height: 1.1; }
.page-sub    { font-size: 13px; color: var(--text-3); margin-top: 4px; }
.header-actions { display: flex; gap: 8px; }

.btn { padding:8px 16px; border-radius:8px; font-size:13px; font-weight:600; cursor:pointer; border:none; transition:all 0.15s; font-family: var(--sans); }
.btn-primary { background: var(--navy); color: white; }
.btn-primary:hover { background: var(--navy-mid); }
.btn-outline { background: transparent; color: var(--text-2); border: 1.5px solid var(--border-dark); }
.btn-outline:hover { background: var(--bg); }

/* ── CARDS ── */
.card {
  background: var(--surface); border-radius: var(--radius);
  border: 1px solid var(--border); box-shadow: var(--shadow-sm);
  transition: box-shadow 0.2s, border-color 0.4s;
  position: relative; overflow: hidden;
}
.card:hover { box-shadow: var(--shadow); }
.card-pad { padding: 20px; }

@keyframes cardPulse {
  0%  { border-color: var(--border); box-shadow: var(--shadow-sm); }
  40% { border-color: var(--blue); box-shadow: 0 0 0 3px rgba(59,111,212,0.15), var(--shadow); }
  100%{ border-color: var(--border); box-shadow: var(--shadow-sm); }
}
.card-updated { animation: cardPulse 1.2s ease; }

/* ── KPI ── */
.kpi-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; }
.kpi-card { padding: 20px; }
.kpi-label { font-size:11.5px; font-weight:600; color:var(--text-3); text-transform:uppercase; letter-spacing:.07em; margin-bottom:8px; font-family: var(--sans); }
.kpi-value { font-family:var(--serif); font-size:30px; color:var(--navy); line-height:1; margin-bottom:6px; }
.kpi-sub   { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--text-3); }
.kpi-accent { position:absolute; bottom:0; right:0; width:80px; height:80px; border-radius:50%; opacity:.06; transform:translate(25%,25%); }

.badge { display:inline-flex; align-items:center; gap:3px; padding:2px 7px; border-radius:20px; font-size:11.5px; font-weight:600; }
.badge-up   { background:var(--emerald-bg); color:var(--emerald); }
.badge-down { background:var(--coral-bg);   color:var(--coral); }
.badge-flat { background:var(--amber-bg);   color:var(--amber); }

/* legacy aliases */
.badge-cheap { display:inline-flex;align-items:center;padding:2px 8px;border-radius:20px;font-size:11.5px;font-weight:600;background:var(--emerald-bg);color:var(--emerald); }
.badge-rich  { display:inline-flex;align-items:center;padding:2px 8px;border-radius:20px;font-size:11.5px;font-weight:600;background:var(--coral-bg);color:var(--coral); }
.badge-fair  { display:inline-flex;align-items:center;padding:2px 8px;border-radius:20px;font-size:11.5px;font-weight:600;background:var(--amber-bg);color:var(--amber); }

/* ── DASHBOARD GRID ── */
/* Layout: chart (col1-2 row1) | holdings (col3 rows1-2)
           health (col1 row2)  | sector   (col2 row2)
   Health and Sector share the same row → equal height automatically. */
.dashboard-grid { display:grid; grid-template-columns:1fr 1fr 340px; grid-template-rows:auto auto; gap:18px; align-items:stretch; }
.portfolio-chart-card { grid-column: 1 / 3; }
.holdings-card { grid-column: 3; grid-row: 1 / 3; display:flex; flex-direction:column; }
.health-card   { grid-column: 1; }
.sector-card   { grid-column: 2; }

/* ── CARD HEADER ── */
.card-header { display:flex; align-items:center; justify-content:space-between; padding:18px 20px 0; margin-bottom:14px; }
.card-title-serif { font-family:var(--serif); font-size:18px; color:var(--navy); }
.card-action { font-size:12px; color:var(--blue); cursor:pointer; font-weight:600; }
.chart-tabs { display:flex; gap:4px; }
.chart-tab { padding:4px 10px; border-radius:6px; font-size:11.5px; font-weight:600; cursor:pointer; color:var(--text-3); transition:all 0.15s; border:none; background:none; font-family:var(--sans); }
.chart-tab.active { background:var(--navy); color:white; }
.chart-tab:hover:not(.active) { background:var(--bg); color:var(--text); }
.chart-wrap { padding:0 20px 20px; height:220px; }

/* ── HEALTH ── */
.health-ring-wrap { display:flex; justify-content:center; padding:16px 0 8px; position:relative; }
.ring-center { position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); text-align:center; }
.ring-score  { font-family:var(--serif); font-size:36px; color:var(--navy); line-height:1; }
.ring-label  { font-size:11px; color:var(--text-3); font-weight:600; text-transform:uppercase; letter-spacing:.05em; }
.health-metrics  { padding:0 20px 20px; }
.health-metric   { display:flex; align-items:center; justify-content:space-between; padding:10px 0; border-bottom:1px solid var(--border); }
.health-metric:last-child { border-bottom:none; }
.hm-left { flex:1; }
.hm-name { font-size:13px; font-weight:500; color:var(--text); }
.hm-desc { font-size:11px; color:var(--text-4); margin-top:1px; }
.hm-right { display:flex; flex-direction:column; align-items:flex-end; gap:4px; }
.hm-bar-wrap { width:80px; height:5px; background:var(--border); border-radius:10px; overflow:hidden; }
.hm-bar { height:100%; border-radius:10px; transition:width 0.8s ease; }
.hm-score { font-size:11.5px; font-weight:700; font-family:var(--mono); }

/* ── HOLDINGS TABLE ── */
/* holdings-card now spans the full right column → allow inner scroll */
.holdings-card .card { flex:1; display:flex; flex-direction:column; }
.holdings-card > .card > div { flex:1; overflow-y:auto; }
.holdings-table { width:100%; border-collapse:collapse; }
.holdings-table th { padding:10px 12px; font-size:10.5px; font-weight:600; color:var(--text-4); text-transform:uppercase; letter-spacing:.07em; text-align:right; border-bottom:1px solid var(--border); white-space:nowrap; }
.holdings-table th:first-child { text-align:left; }
.holdings-table td { padding:11px 12px; text-align:right; border-bottom:1px solid var(--border); color:var(--text-2); font-family:var(--mono); font-size:12.5px; }
.holdings-table tr:last-child td { border-bottom:none; }
.holdings-table tr:hover td { background:var(--bg); }
.holdings-table td:first-child { text-align:left; font-family:var(--sans); font-weight:600; color:var(--text); font-size:13px; }
.pool-name { font-size:13px; font-weight:600; color:var(--text); }
.pool-sub  { font-size:11px; color:var(--text-4); font-weight:400; font-family:var(--sans); margin-top:1px; }

/* ── SECTOR ── */
.sector-list { padding:0 20px 16px; }
.sector-row  { display:flex; align-items:center; gap:10px; padding:8px 0; border-bottom:1px solid var(--border); }
.sector-row:last-child { border-bottom:none; }
.sector-color { width:10px; height:10px; border-radius:3px; flex-shrink:0; }
.sector-name  { flex:1; font-size:13px; font-weight:500; color:var(--text); }
.sector-bar-wrap { width:100px; height:6px; background:var(--border); border-radius:10px; overflow:hidden; }
.sector-bar  { height:100%; border-radius:10px; transition:width 0.8s ease; }
.sector-pct  { font-size:12.5px; font-weight:700; font-family:var(--mono); width:36px; text-align:right; color:var(--text-2); }

/* ── BOTTOM GRID ── */
.bottom-grid { display:grid; grid-template-columns:1fr 1fr; gap:18px; }

/* ── PERFORMERS ── */
.performer-list { padding:0 20px 16px; }
.performer-col-hdr {
  display:flex; align-items:center; gap:12px;
  padding:6px 20px 4px;
  border-bottom:1px solid var(--border-dark);
}
.performer-col-hdr span {
  font-size:10px; font-weight:700; color:var(--text-4);
  text-transform:uppercase; letter-spacing:.06em; font-family:var(--sans);
}
.performer-col-rank  { width:18px; flex-shrink:0; }
.performer-col-pool  { flex:1; }
.performer-col-trend { width:60px; flex-shrink:0; }
.performer-col-ret   { min-width:60px; text-align:right; flex-shrink:0; }
.performer-row  { display:flex; align-items:center; gap:12px; padding:10px 0; border-bottom:1px solid var(--border); }
.performer-row:last-child { border-bottom:none; }
.performer-rank { font-size:11px; font-weight:700; color:var(--text-4); font-family:var(--mono); width:18px; flex-shrink:0; }
.performer-info { flex:1; }
.performer-name { font-size:13px; font-weight:600; color:var(--text); }
.performer-type { font-size:11px; color:var(--text-4); }
.performer-chart { display:block; flex-shrink:0; }
.performer-return { font-size:14px; font-weight:700; font-family:var(--mono); color:var(--emerald); text-align:right; min-width:60px; flex-shrink:0; }
.performer-return.neg { color:var(--coral); }

/* ── WATCHLIST ── */
.watch-list { padding:0 20px 16px; }
.watch-row  { display:flex; align-items:center; gap:10px; padding:10px 0; border-bottom:1px solid var(--border); cursor:pointer; transition:background 0.1s; }
.watch-row:last-child { border-bottom:none; }
.watch-row:hover { background:var(--bg); margin:0 -20px; padding:10px 20px; }
.watch-star { color:var(--amber); font-size:14px; }
.watch-info { flex:1; }
.watch-name { font-size:13px; font-weight:600; color:var(--text); }
.watch-meta { font-size:11px; color:var(--text-4); }
.watch-price { text-align:right; font-family:var(--mono); }
.watch-price-val { font-size:13.5px; font-weight:600; color:var(--text); }
.watch-price-chg { font-size:11.5px; margin-top:1px; }

/* ── INNER GRADIO COMPONENTS (inside tabs) ── */
.nexus-tab-content .block { background: var(--surface) !important; border: 1px solid var(--border) !important; border-radius: var(--radius) !important; box-shadow: var(--shadow-sm) !important; }
.nexus-tab-content .block:hover { box-shadow: var(--shadow) !important; }
/* Tab page header — transparent, no card border */
.nexus-tab-content .nexus-tab-hdr.block { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; margin-bottom: 4px !important; }
.nexus-tab-content .nexus-tab-hdr.block:hover { box-shadow: none !important; }

input[type="text"], input[type="number"], textarea, select { background: #F1F5F9 !important; border: 1.5px solid transparent !important; color: var(--text) !important; font-family: var(--mono) !important; font-size: 12.5px !important; border-radius: 8px !important; transition: all 0.2s !important; }
input:focus, textarea:focus, select:focus { background: var(--surface) !important; border-color: var(--blue) !important; outline: none !important; box-shadow: 0 0 0 3px rgba(59,111,212,0.1) !important; }

button.primary { background: var(--navy) !important; color: #fff !important; font-family: var(--sans) !important; font-weight: 600 !important; border: none !important; border-radius: 8px !important; }
button.primary:hover { background: var(--navy-mid) !important; }
button.secondary { background: var(--surface) !important; color: var(--text-2) !important; border: 1.5px solid var(--border-dark) !important; border-radius: 8px !important; font-family: var(--sans) !important; }
button:hover { border-color: var(--blue) !important; color: var(--blue) !important; }

.tabs > .tab-nav { background: var(--surface) !important; border-bottom: 1px solid var(--border) !important; }
.tabs > .tab-nav button { color: var(--text-3) !important; font-family: var(--sans) !important; font-size: 13px !important; font-weight: 500 !important; border-bottom: 2px solid transparent !important; padding: 8px 16px !important; background: transparent !important; }
.tabs > .tab-nav button.selected { color: var(--blue) !important; border-bottom-color: var(--blue) !important; font-weight: 600 !important; }
.tabs > .tab-nav button:hover { color: var(--text) !important; background: var(--bg) !important; }

table { border-collapse: collapse !important; width: 100% !important; font-family: var(--mono) !important; font-size: 12.5px !important; }
th { background: #F1F5F9 !important; color: var(--text-4) !important; font-weight: 600 !important; font-size: 10.5px !important; text-transform: uppercase !important; letter-spacing: .07em !important; padding: 10px 12px !important; border-bottom: 1px solid var(--border) !important; white-space: nowrap !important; }
tr { border-bottom: 1px solid var(--border) !important; }
tr:hover { background: var(--bg) !important; }
td { padding: 10px 12px !important; color: var(--text-2) !important; font-family: var(--mono) !important; }
label { color: var(--text-3) !important; font-size: 11px !important; font-weight: 600 !important; text-transform: uppercase !important; letter-spacing: .07em !important; font-family: var(--sans) !important; }
input[type="range"] { accent-color: var(--blue) !important; }

::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border-dark); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--blue); }

/* status/delta helpers */
.delta-pos { color: var(--emerald); font-family: var(--mono); }
.delta-neg { color: var(--coral);   font-family: var(--mono); }

/* ── HIDDEN COLUMNS (market pills, scenario selector) ── */
#nexus-market-hidden-col { position: absolute !important; top: -9999px !important; left: -9999px !important; width: 0 !important; overflow: hidden !important; }

/* ── SIDEBAR INNER fills column ── */
#nexus-sidebar-inner { display: flex; flex-direction: column; height: 100%; }
#nexus-sidebar-col > .block { padding: 0 !important; height: 100% !important; }

/* ── CHAT clear row ── */

/* ── DASHBOARD HTML fills tab ── */
#nexus-dashboard-html { display: block; }
#nexus-dashboard-html > .block { padding: 0 !important; border: none !important; box-shadow: none !important; background: transparent !important; }
.status-ok     { color: var(--emerald); }
.status-warn   { color: var(--amber); }
.status-breach { color: var(--coral); font-weight: 700; }
.section-hdr { font-family: var(--sans); font-size: 10.5px; font-weight: 600; color: var(--text-4); text-transform: uppercase; letter-spacing: .08em; padding: 6px 0; border-bottom: 1px solid var(--border); margin-bottom: 8px; }
.analytics-table { width:100%; border-collapse:collapse; font-family:var(--mono); font-size:12.5px; }
.analytics-table td { padding:10px 12px; border-bottom:1px solid var(--border); }

/* ── Security Analytics tab ──────────────────────────────────────────── */

/* Results table */
.nexus-sa-count p  { font-size: 12px; font-weight: 500; color: var(--text-2); margin: 0 0 4px 0; }
.nexus-sa-hint  p  { font-size: 11px; color: var(--text-4); margin: 4px 0 0 0; }

/* Results table rows — hover hint */
.nexus-tab-content .table-wrap table tbody tr { cursor: pointer; transition: background .12s; }
.nexus-tab-content .table-wrap table tbody tr:hover { background: #EEF2FF !important; }

/* Shock table — highlight BAU row (4th data row = index 3) */
.nexus-tab-content .table-wrap table tbody tr:nth-child(4) td { font-weight: 600; background: #F0F4FF; }

/* Animations */
@keyframes fadeUp   { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
@keyframes livepulse{ 0%,100%{opacity:1} 50%{opacity:.4} }
@keyframes cardPulseKpi { 0%{border-color:var(--border)} 40%{border-color:var(--blue)} 100%{border-color:var(--border)} }
.fade-up { animation: fadeUp 0.4s ease both; }
"""


def get_theme() -> gr.themes.Base:
    """Gradio theme — sizing only; all visuals come from CUSTOM_CSS."""
    return gr.themes.Base(
        spacing_size=gr.themes.sizes.spacing_sm,
        radius_size=gr.themes.sizes.radius_sm,
        text_size=gr.themes.sizes.text_sm,
    )
