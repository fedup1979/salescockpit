# Sales Cockpit Product Context

## Register

Product.

## Product Purpose

Sales Cockpit is an internal ESSR sales tool that replaces Front.io for WhatsApp sales operations while keeping SchoolDrive as the source of truth.

The tool helps setters and closers manage WhatsApp conversations, call tasks, templates, lead qualification, and follow-up work without violating WhatsApp Business API rules.

## Users

- Admins: Laura, François, Tiago.
- Setter: Mihary.
- Closer: Yasmine.
- Future setters and closers.

## Primary Jobs

- See active WhatsApp leads and conversations.
- Know whether the WhatsApp 24-hour window is open or closed.
- Send free-form messages only when allowed.
- Use approved templates when the 24-hour window is closed.
- Create templates when no template fits.
- Manage call tasks.
- Qualify leads.
- Preserve complete conversation history for a future AI setter.

## UX Principles

- Operational density over marketing polish.
- No ambiguous send states.
- Every blocked action must explain why it is blocked.
- The inbox must be scannable in seconds.
- The conversation view must make the next action obvious.
- The UI should feel like a calm internal sales console, not a landing page.

## Anti-References

- Front.io complexity and poor fit for ESSR sales workflow.
- Heavy CRM interfaces.
- Decorative dashboards.
- WhatsApp Web scraping or unofficial integrations.

## Strategic Principles

- SchoolDrive remains the source of truth.
- Notion is read-only historical context.
- Twilio is the WhatsApp provider.
- SQLite WAL is acceptable for the MVP.
- The data model must preserve messages, events, outcomes, and labels for future AI learning.
