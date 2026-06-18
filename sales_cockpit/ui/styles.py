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

header[data-testid="stHeader"] {
  height: 0;
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
  max-width: 1440px;
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

.sc-compact-state span {
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  padding: .18rem .5rem;
  border: 1px solid var(--sc-border);
  border-radius: 999px;
  background: oklch(0.99 0.004 250);
  color: var(--sc-muted);
  font-size: .78rem;
  line-height: 1.2;
}

.sc-compact-state strong {
  color: var(--sc-text);
  font-weight: 650;
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

.sc-badge-neutral {
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
  background: oklch(0.985 0.012 215);
}

.sc-message-outbound {
  background: oklch(0.972 0.018 145);
}

.sc-message-note {
  background: oklch(0.972 0.018 82);
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

.sc-reply-anchor {
  margin-top: 1.1rem;
  padding-top: .85rem;
  border-top: 1px solid var(--sc-border);
}

.sc-template-preview {
  border: 1px solid var(--sc-border);
  border-radius: 8px;
  padding: .75rem .85rem;
  background: oklch(0.982 0.01 145);
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

.sc-compact-label {
  color: var(--sc-muted);
  font-size: .75rem;
  text-transform: uppercase;
  letter-spacing: 0;
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
</style>
"""
