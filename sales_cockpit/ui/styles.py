APP_CSS = """
<style>
:root {
  --sc-bg: oklch(0.985 0.006 250);
  --sc-panel: oklch(0.958 0.007 250);
  --sc-border: oklch(0.865 0.012 250);
  --sc-text: oklch(0.245 0.018 250);
  --sc-muted: oklch(0.52 0.018 250);
  --sc-accent: oklch(0.54 0.14 250);
  --sc-success: oklch(0.55 0.13 145);
  --sc-warning: oklch(0.72 0.16 82);
  --sc-danger: oklch(0.58 0.18 29);
}

.stApp {
  background: var(--sc-bg);
  color: var(--sc-text);
}

[data-testid="stSidebar"] {
  background: var(--sc-panel);
  border-right: 1px solid var(--sc-border);
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span {
  color: var(--sc-text) !important;
}

[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * {
  color: var(--sc-muted) !important;
}

[data-testid="stSidebar"] [role="radiogroup"] label {
  border-radius: 8px;
  padding: .18rem .28rem;
}

[data-testid="stSidebar"] [role="radiogroup"] label:hover {
  background: oklch(0.93 0.012 250);
}

[data-testid="stSidebar"] [role="radiogroup"] [aria-checked="true"] {
  color: var(--sc-danger) !important;
}

[data-testid="stSidebar"] .stButton > button {
  color: var(--sc-text) !important;
  background: oklch(0.985 0.006 250) !important;
  border: 1px solid var(--sc-border) !important;
  box-shadow: none !important;
}

[data-testid="stSidebar"] .stButton > button:hover {
  color: var(--sc-accent) !important;
  background: oklch(0.935 0.012 250) !important;
  border-color: var(--sc-accent) !important;
}

header[data-testid="stHeader"] {
  background: transparent;
}

[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"] {
  display: none;
}

.block-container {
  padding-top: .85rem;
  padding-bottom: 2rem;
  padding-left: 1.75rem;
  padding-right: 1.75rem;
  max-width: min(1720px, calc(100vw - 2rem));
}

.st-key-mobile_nav {
  display: none;
}

h1, h2, h3 {
  letter-spacing: 0;
}

.sc-detail-title {
  color: var(--sc-text);
  font-size: 1.5rem;
  font-weight: 600;
  line-height: 1.25;
}

.sc-search-field-offset {
  height: 1.72rem;
}

.sc-topline {
  display: flex;
  gap: .5rem;
  align-items: center;
  color: var(--sc-muted);
  font-size: .85rem;
  margin-bottom: .5rem;
}

.sc-conversation-meta-bar {
  display: flex;
  justify-content: space-between;
  gap: .8rem;
  align-items: flex-start;
  color: var(--sc-muted);
  font-size: .85rem;
  margin: .15rem 0 .55rem 0;
}

.sc-prospect-meta {
  display: flex;
  gap: .45rem;
  flex-wrap: wrap;
  min-width: 0;
  line-height: 1.35;
}

.sc-prospect-meta span + span::before {
  content: "·";
  margin-right: .45rem;
  color: oklch(0.66 0.014 250);
}

.sc-window-status {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: .16rem;
  margin-left: auto;
  white-space: nowrap;
}

.sc-window-close {
  color: var(--sc-muted);
  font-size: .76rem;
  line-height: 1.2;
}

.sc-compact-state {
  display: flex;
  gap: .45rem;
  flex-wrap: wrap;
  align-items: center;
  margin: .35rem 0 .7rem 0;
}

.st-key-lead_state_header .sc-compact-state {
  display: block;
  width: 100%;
}

.sc-compact-state > span {
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  padding: .12rem .45rem;
  border: 1px solid var(--sc-border);
  border-radius: 6px;
  background: oklch(0.99 0.004 250);
  color: var(--sc-muted);
  font-size: .74rem;
  line-height: 1.1;
  min-height: 1.65rem;
}

.st-key-lead_state_header .sc-compact-state > span {
  width: 100%;
  min-height: 2rem;
  justify-content: flex-start;
}

.st-key-lead_qualification_chip,
.st-key-lead_contact_chip {
  position: relative;
}

.st-key-lead_qualification_chip [data-testid="stPopover"],
.st-key-lead_contact_chip [data-testid="stPopover"] {
  position: absolute;
  inset: .35rem 0 .7rem 0;
  z-index: 2;
  margin: 0;
}

.st-key-lead_qualification_chip [data-testid="stPopover"] button,
.st-key-lead_contact_chip [data-testid="stPopover"] button {
  width: 100%;
  height: 100%;
  min-height: 1.65rem;
  padding: 0;
  border: 0 !important;
  background: transparent !important;
  color: transparent !important;
  box-shadow: none !important;
  cursor: pointer;
}

.st-key-lead_qualification_chip:hover .sc-clickable-state > span,
.st-key-lead_contact_chip:hover .sc-clickable-state > span {
  border-color: oklch(0.68 0.05 250);
  color: var(--sc-text);
}

.sc-compact-state > span > span,
.sc-compact-state strong {
  display: inline-flex;
  align-items: center;
  line-height: 1.1;
}

.sc-compact-state strong {
  color: var(--sc-text);
  font-weight: 650;
}

.sc-planned-call-notice {
  display: flex;
  justify-content: space-between;
  gap: .75rem;
  align-items: center;
  margin: .3rem 0 .75rem 0;
  padding: .55rem .7rem;
  border: 1px solid oklch(0.78 0.07 250);
  border-radius: 8px;
  background: oklch(0.965 0.018 250);
  color: var(--sc-text);
  font-size: .86rem;
}

.sc-planned-call-notice span {
  color: var(--sc-muted);
  text-align: right;
}

.sc-action-banner {
  margin: .2rem 0 .9rem 0;
  padding: .75rem .9rem;
  border: 1px solid var(--sc-border);
  border-radius: 8px;
  background: oklch(0.968 0.014 250);
  color: var(--sc-text);
}

.sc-action-banner-blue {
  border-color: oklch(0.78 0.07 250);
  background: oklch(0.965 0.018 250);
}

.sc-action-banner-orange {
  border-color: oklch(0.78 0.11 82);
  background: oklch(0.965 0.026 82);
}

.sc-action-banner-red {
  border-color: oklch(0.75 0.11 29);
  background: oklch(0.965 0.022 29);
}

.sc-action-banner-title {
  font-weight: 700;
  line-height: 1.2;
  margin-bottom: .18rem;
}

.sc-action-banner-body {
  color: var(--sc-muted);
  font-size: .88rem;
  line-height: 1.35;
}

.sc-badge {
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  padding: .15rem .45rem;
  border-radius: 999px;
  border: 1px solid var(--sc-border);
  font-size: .78rem;
  font-weight: 600;
}

.sc-badge-open {
  color: oklch(0.36 0.12 145);
  background: oklch(0.94 0.04 145);
}

.sc-badge-closed {
  color: oklch(0.38 0.12 29);
  background: oklch(0.94 0.035 29);
}

.sc-badge-muted {
  color: var(--sc-muted);
  background: oklch(0.97 0.006 250);
}

@media (max-width: 760px) {
  .sc-conversation-meta-bar {
    flex-direction: column;
  }

  .sc-window-status {
    align-items: flex-start;
    margin-left: 0;
  }

  .sc-planned-call-notice {
    align-items: flex-start;
    flex-direction: column;
  }

  .sc-planned-call-notice span {
    text-align: left;
  }

}

.sc-message {
  border: 1px solid var(--sc-border);
  border-radius: 8px;
  padding: .7rem .8rem;
  margin: .45rem 0;
  background: oklch(0.995 0.004 250);
  max-width: min(76%, 680px);
  line-height: 1.45;
}

.sc-message-inbound {
  background: oklch(0.952 0.038 218);
  border-color: oklch(0.78 0.065 218);
}

.sc-message-outbound {
  background: oklch(0.94 0.052 145);
  border-color: oklch(0.76 0.085 145);
}

.sc-message-note {
  background: oklch(0.95 0.065 86);
  border-color: oklch(0.76 0.105 86);
  max-width: min(86%, 760px);
}

.sc-message-meta {
  color: var(--sc-muted);
  font-size: .78rem;
  margin-bottom: .2rem;
}

.sc-message-row {
  display: flex;
  width: 100%;
}

.sc-message-row-inbound {
  justify-content: flex-start;
}

.sc-message-row-outbound {
  justify-content: flex-end;
}

.sc-message-row-note {
  justify-content: center;
}

.sc-message-row-outbound .sc-message-meta {
  text-align: right;
}

.sc-delivery-status {
  display: inline-block;
  margin-left: .28rem;
  font-size: .84rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  vertical-align: baseline;
}

.sc-delivery-pending {
  color: oklch(0.55 0.018 250);
}

.sc-delivery-sent,
.sc-delivery-delivered {
  color: oklch(0.48 0.025 250);
}

.sc-delivery-read {
  color: oklch(0.58 0.15 230);
}

.sc-delivery-failed {
  color: oklch(0.52 0.17 28);
}

.sc-journal-table {
  width: 100%;
  table-layout: fixed;
  border-collapse: separate;
  border-spacing: 0;
  margin-top: .7rem;
  border: 1px solid var(--sc-border);
  border-radius: 8px;
  overflow: hidden;
  background: oklch(0.995 0.004 250);
}

.sc-journal-table th {
  padding: .5rem .65rem;
  background: oklch(0.955 0.007 250);
  border-bottom: 1px solid var(--sc-border);
  color: var(--sc-muted);
  font-size: .75rem;
  font-weight: 700;
  text-align: left;
  text-transform: uppercase;
}

.sc-journal-table th:nth-child(1),
.sc-journal-table td:nth-child(1) {
  width: 10.5rem;
}

.sc-journal-table th:nth-child(2),
.sc-journal-table td:nth-child(2) {
  width: 10rem;
}

.sc-journal-table td {
  padding: .48rem .65rem;
  border-bottom: 1px solid oklch(0.91 0.008 250);
  color: var(--sc-text);
  font-size: .86rem;
  line-height: 1.35;
  vertical-align: top;
}

.sc-journal-table tr:last-child td {
  border-bottom: 0;
}

.sc-journal-time {
  color: var(--sc-muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.sc-journal-description {
  overflow-wrap: anywhere;
  white-space: normal;
  word-break: normal;
}

.sc-journal-badge {
  display: inline-flex;
  align-items: center;
  min-height: 1.35rem;
  padding: .08rem .42rem;
  border: 1px solid var(--sc-border);
  border-radius: 999px;
  background: oklch(0.97 0.006 250);
  color: var(--sc-muted);
  font-size: .75rem;
  font-weight: 650;
  white-space: normal;
}

@media (max-width: 760px) {
  .sc-journal-table {
    table-layout: auto;
  }

  .sc-journal-table th:nth-child(1),
  .sc-journal-table td:nth-child(1),
  .sc-journal-table th:nth-child(2),
  .sc-journal-table td:nth-child(2) {
    width: auto;
  }
}

.sc-attachment-list {
  display: flex;
  flex-wrap: wrap;
  gap: .35rem;
  margin-top: .45rem;
}

.sc-attachment-link {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: .16rem .45rem;
  border: 1px solid var(--sc-border);
  border-radius: 999px;
  background: oklch(0.985 0.006 250);
  color: var(--sc-text);
  font-size: .76rem;
  line-height: 1.2;
  text-decoration: none;
  overflow-wrap: anywhere;
}

.sc-attachment-link:hover {
  border-color: var(--sc-accent);
}

.sc-reply-anchor {
  margin-top: 1.1rem;
  padding-top: .85rem;
  border-top: 1px solid var(--sc-border);
}

.sc-template-preview {
  border: 1px solid var(--sc-border);
  border-radius: 8px;
  padding: .75rem .85rem;
  background: oklch(0.965 0.025 145);
  margin: .5rem 0 .75rem 0;
  white-space: pre-wrap;
}

.sc-panel {
  border: 1px solid var(--sc-border);
  border-radius: 8px;
  padding: .85rem;
  background: oklch(0.99 0.004 250);
}

.sc-row-meta {
  color: var(--sc-muted);
  font-size: .78rem;
  margin-top: .22rem;
  line-height: 1.28;
}

.sc-preview {
  color: oklch(0.42 0.018 250);
  font-size: .86rem;
  margin-top: .38rem;
  margin-bottom: .24rem;
  line-height: 1.36;
}

.sc-conversation-row {
  padding: .2rem 0 .36rem 0;
}

.sc-lead-type-line {
  color: var(--sc-accent);
  font-size: .7rem;
  font-weight: 700;
  line-height: 1.2;
  margin-bottom: .12rem;
  text-transform: uppercase;
  letter-spacing: 0;
}

.sc-identity-badge {
  display: inline-flex;
  align-items: center;
  margin-left: .4rem;
  padding: .08rem .38rem;
  border: 1px solid oklch(0.82 0.085 82);
  border-radius: 999px;
  background: oklch(0.97 0.035 82);
  color: oklch(0.42 0.095 42);
  font-size: .68rem;
  font-weight: 760;
  text-transform: none;
}

.sc-conversation-title {
  color: var(--sc-text);
  font-size: .98rem;
  line-height: 1.28;
}

.sc-next-action-line {
  color: var(--sc-text);
  font-size: .84rem;
  margin-top: .34rem;
  line-height: 1.32;
}

.sc-next-action-line span {
  color: var(--sc-accent);
  font-weight: 650;
}

.sc-hot-signal {
  display: inline-flex;
  align-items: center;
  gap: .25rem;
  margin-top: .38rem;
  color: oklch(0.42 0.095 42);
  background: oklch(0.94 0.055 58);
  border: 1px solid oklch(0.84 0.085 58);
  border-radius: 999px;
  padding: .12rem .48rem;
  font-size: .78rem;
  font-weight: 680;
  line-height: 1.25;
}

.sc-compact-label {
  color: var(--sc-muted);
  font-size: .75rem;
  text-transform: uppercase;
  letter-spacing: 0;
}

.st-key-next_action_summary_box {
  position: relative;
}

.sc-action-panel {
  display: flex;
  justify-content: space-between;
  gap: .8rem;
  align-items: flex-start;
  border: 1px solid var(--sc-border);
  border-radius: 8px;
  padding: .75rem .85rem;
  margin: .65rem 0 1rem 0;
  background: oklch(0.99 0.004 250);
}

.st-key-next_action_summary_box [data-testid="stPopover"] {
  position: absolute;
  top: 3.25rem;
  right: .85rem;
  z-index: 2;
  width: 2rem;
  margin: 0;
}

.st-key-next_action_summary_box [data-testid="stPopover"] button {
  width: 2rem;
  min-height: 1.9rem;
  padding: 0;
  border: 1px solid oklch(0.72 0.14 29) !important;
  border-radius: 6px;
  background: oklch(0.965 0.022 29) !important;
  color: oklch(0.48 0.17 29) !important;
  box-shadow: none !important;
  font-size: .98rem;
  font-weight: 760;
  justify-content: center;
}

.st-key-next_action_summary_box [data-testid="stPopover"] button [aria-hidden="true"],
.st-key-next_action_summary_box [data-testid="stPopover"] button [data-testid="stIconMaterial"] {
  display: none;
}

.st-key-next_action_summary_box [data-testid="stPopover"] button > div {
  width: 100%;
  justify-content: center;
}

.st-key-next_action_summary_box [data-testid="stPopover"] button:hover {
  border-color: oklch(0.58 0.18 29) !important;
  background: oklch(0.94 0.04 29) !important;
  color: oklch(0.38 0.16 29) !important;
}

.sc-action-title {
  font-weight: 680;
  line-height: 1.3;
  margin-top: .12rem;
}

.sc-action-badges {
  display: flex;
  gap: .35rem;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.sc-action-description {
  margin-top: .55rem;
  color: var(--sc-text);
  white-space: pre-wrap;
  line-height: 1.4;
}

.sc-link-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 2.45rem;
  padding: .42rem .7rem;
  border: 1px solid var(--sc-border);
  border-radius: 8px;
  background: oklch(0.99 0.004 250);
  color: var(--sc-text);
  text-decoration: none;
  font-size: .88rem;
  font-weight: 600;
}

.sc-link-button:hover {
  border-color: var(--sc-accent);
  color: var(--sc-accent);
}

.sc-readiness {
  border: 1px solid var(--sc-border);
  border-radius: 8px;
  padding: .75rem .8rem;
  background: oklch(0.99 0.004 250);
  min-height: 7rem;
}

.sc-readiness-label {
  color: var(--sc-muted);
  font-size: .78rem;
  font-weight: 650;
  line-height: 1.2;
  margin-bottom: .42rem;
}

.sc-readiness-state {
  color: var(--sc-text);
  font-size: 1rem;
  font-weight: 720;
  line-height: 1.22;
  margin-bottom: .32rem;
}

.sc-readiness-detail {
  color: var(--sc-muted);
  font-size: .8rem;
  line-height: 1.32;
}

.sc-wrapped-table-frame {
  max-height: 42rem;
  overflow: auto;
  border: 1px solid var(--sc-border);
  border-radius: 8px;
  background: oklch(0.99 0.004 250);
}

.sc-wrapped-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: .82rem;
  line-height: 1.34;
}

.sc-wrapped-table th,
.sc-wrapped-table td {
  padding: .48rem .55rem;
  border-bottom: 1px solid var(--sc-border);
  border-right: 1px solid var(--sc-border);
  color: var(--sc-text);
  vertical-align: top;
  white-space: normal;
  overflow-wrap: anywhere;
}

.sc-wrapped-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--sc-panel);
  color: var(--sc-muted);
  font-weight: 700;
}

.sc-wrapped-table th:last-child,
.sc-wrapped-table td:last-child {
  width: 32%;
}

.sc-readiness-ready {
  border-color: oklch(0.78 0.07 145);
  background: oklch(0.968 0.025 145);
}

.sc-readiness-info {
  border-color: oklch(0.8 0.055 230);
  background: oklch(0.97 0.018 230);
}

.sc-readiness-warning {
  border-color: oklch(0.82 0.085 82);
  background: oklch(0.97 0.035 82);
}

.sc-readiness-danger {
  border-color: oklch(0.78 0.09 29);
  background: oklch(0.97 0.026 29);
}

.sc-status-panel {
  border: 1px solid var(--sc-border);
  border-radius: 8px;
  padding: .7rem .8rem;
  background: oklch(0.99 0.004 250);
  margin: .2rem 0 .7rem 0;
}

.sc-status-panel strong {
  display: block;
  color: var(--sc-text);
  font-size: 1.1rem;
  line-height: 1.2;
  margin-bottom: .18rem;
}

.sc-status-panel span {
  color: var(--sc-muted);
  font-size: .82rem;
  line-height: 1.34;
}

div[data-testid="stAlert"] {
  margin: .45rem 0 .7rem 0;
}

div[data-testid="stCheckbox"] label,
div[data-testid="stCheckbox"] span {
  color: var(--sc-text) !important;
}

@media (max-width: 900px) {
  .block-container {
    padding-left: 1rem;
    padding-right: 1rem;
    max-width: 100%;
  }

  .st-key-mobile_nav {
    display: block;
    position: sticky;
    top: .35rem;
    z-index: 20;
    padding: .55rem .65rem .65rem .65rem;
    margin: .1rem 0 .85rem 0;
    border: 1px solid var(--sc-border);
    border-radius: 8px;
    background: oklch(0.985 0.006 250);
    box-shadow: 0 8px 18px oklch(0.45 0.02 250 / 0.08);
  }

  .st-key-mobile_nav label,
  .st-key-mobile_nav span {
    color: var(--sc-text) !important;
  }

  .sc-search-field-offset {
    height: .25rem;
  }

  .sc-detail-title {
    font-size: 1.25rem;
  }

  .sc-message {
    max-width: 94%;
  }

  .sc-action-panel {
    flex-direction: column;
  }

  .sc-action-badges {
    justify-content: flex-start;
  }
}
</style>
"""
