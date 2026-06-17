# Sales Cockpit Design Context

## Design Register

Product UI.

## Scene

Sales users work during the day on laptops, often switching quickly between calls, WhatsApp replies, SchoolDrive, and follow-up tasks. The interface must stay light, readable, and calm under pressure.

## Theme

Light interface with restrained color. This is a work cockpit, not a campaign page.

## Color Strategy

Restrained.

- Main surface: tinted off-white.
- Sidebar and panels: slightly cooler neutral.
- Primary accent: controlled blue for actions and current selection.
- Success: green.
- Warning: amber.
- Error: red.
- Info: blue.

Use OKLCH values in CSS where custom CSS is written.

## Typography

Use system fonts. Keep labels compact and readable. Avoid display typography.

## Layout

- Inbox first.
- Dense but not cramped.
- Left navigation, central work area, right detail panel when useful.
- Cards only for repeated entities or bounded panels.
- No nested cards.

## Components

- Buttons use consistent shape and states.
- Status badges are compact.
- Window state must be visually obvious.
- Disabled send controls must show why.
- Tables and lists must prioritize scanning.

## Interaction

- Template search should be immediate.
- Lead search should be global.
- Call tasks should be one click to create and one click to complete.
- Manual private WhatsApp notes must be clearly distinguished from official Twilio messages.

## Accessibility

- Do not rely on color alone for WhatsApp window state.
- Use readable contrast.
- Keep focus order predictable.
