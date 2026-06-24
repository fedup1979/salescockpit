# Sales Cockpit Gap Analysis

This document is a current gap analysis, not a historical build plan. For live environment status, read `docs/CURRENT_STATE.md` first.

## Current Baseline

Sales Cockpit now has the main V1 workflow foundations:

- local users and roles;
- conversation state, shown as active or terminated;
- WhatsApp 24h window enforcement;
- SchoolDrive webhook ingestion;
- Twilio inbound/status endpoints and template synchronization;
- Front read-only buffer foundation;
- Pilotage for flux steps and template mapping;
- action workflow with reply, follow-up, setting call, closing call and contact review;
- planned call preservation when a prospect writes before the call;
- course-start follow-up logic that does not interrupt planned calls;
- readiness checks for workflow consistency;
- staging deployment on DigitalOcean;
- cold production deployment with Twilio mock mode.

## Canonical Model

The model to preserve is:

- `Parcours`: commercial state of the prospect, derived from workflow outcomes.
- `Flux`: configurable follow-up scenario that creates future actions.
- `Action`: concrete work item in the queue.

A conversation with `open` status normally has one active main next action.

Canonical exception: if a prospect writes while a setting/closing call is already planned, Sales Cockpit can temporarily have two active main actions for that conversation:

- urgent `reply` for Setter I;
- already planned `setting_call` or `closing_call`.

After the reply is sent, if the appointment is unchanged, the planned call becomes the visible next action again. This is not a workflow error.

## Gaps Before Operational Production

### Live SchoolDrive Path

Still to validate with a fresh real record:

1. website form creates a Lead or Presubscription in SchoolDrive;
2. SchoolDrive posts the snapshot to Sales Cockpit;
3. SchoolDrive sends the automatic WhatsApp autoresponder;
4. AR status changes to `sent`;
5. SchoolDrive posts a newer snapshot;
6. Sales Cockpit stores the sent message body in the thread;
7. Sales Cockpit creates the Tanjona follow-up at `sent_at + 72h`;
8. `pre_cutover_check` stays green.

### Staging Data Hygiene

Staging received a large historical SchoolDrive replay before Tiago added the `created_at >= 2026-03-01` filter. Before final scenario testing, decide whether to:

- keep current staging data if it remains readable;
- clean SchoolDrive-backed staging rows and replay a focused recent set;
- rebuild staging from backup and replay only the validation set.

Always create a restore point before cleanup.

### Twilio Production Safety

The real ESSR Twilio account must remain read-only until explicit cutover.

Current safe posture:

- staging checked in Twilio `mock` mode after the latest workflow deployment;
- production remains Twilio `mock`;
- template synchronization can read real ESSR templates;
- no production WhatsApp webhook or sender configuration should be changed before explicit GO.

### Template Mapping With Laura

Initial template mappings exist for `FSM`, `APP`, and `AS`, but they are an AI-generated starting point.

Laura still needs to validate:

- how many steps each flux should contain;
- timing of each step;
- which approved Twilio template belongs to each flux, course and step;
- whether additional course categories should be activated.

V1 rule: edits affect only newly created future actions. Existing open actions are not recalculated.

### Course-Start Runtime

Implemented guardrail:

- course-start follow-ups use SchoolDrive `course.start_date` or the active default session for the category;
- course-start follow-up can replace a conflicting lead/presubscription follow-up;
- course-start follow-up does not replace planned setting/closing calls.

Remaining gap:

- no global periodic sweep yet. A future task may be needed to detect upcoming course-start relances when no fresh SchoolDrive event arrives.

### Front Historical Import

Front remains read-only.

Current gap:

- not all historical conversations are matched;
- ambiguous phone matches require review;
- full active-conversation conversion into Sales Cockpit actions is not an operational cutover dependency yet.

### Identity Resolution

V1 guardrail exists:

- one phone match attaches automatically;
- zero or multiple matches create an `À identifier` temporary record.

V2 gap:

- recrawl/search SchoolDrive;
- merge temporary records into real SchoolDrive-backed records;
- move conversations, messages, notes, events and actions safely.

## Risks To Watch

### Too Many Active Actions

Risk: users lose clarity if a conversation has multiple unrelated next actions.

Current mitigation:

- readiness check flags open conversations with conflicting main actions;
- the intentional `reply` plus planned call exception is allowed.

### Manual Closure Too Early

Risk: a valid opportunity is closed by mistake.

Current mitigation:

- controlled closure reasons;
- note required for sensitive reasons;
- reactivation requires a note and a new next action.

### Do-Not-Contact Error

Risk: sending to a prospect who asked not to be contacted.

Current mitigation:

- contact status is separate from commercial qualification;
- sends are blocked while `do_not_contact` is active;
- inbound from `do_not_contact` creates a human contact review.

### Wrong Template Mapping

Risk: Tanjona sends an approved but commercially wrong template.

Current mitigation:

- Pilotage shows full message body, Twilio SID and status;
- only approved real Twilio templates can be assigned operationally;
- Laura validation remains required.

### Will-Sign And Personalized Follow-Up Semantics

Open design point from the Laura workflow review:

- after a closer marks a prospect as `will_sign`, the prospect should not silently downgrade to an earlier generic flux such as `setter_no_next_step`;
- `course_start` remains higher priority than `closer_will_sign`, with the 24h spacing rule, but a planned setting/closing call still stays primary;
- before sending a course-start message, Sales Cockpit should rely on a fresh SchoolDrive course-full signal, or later add a pre-send SchoolDrive check;
- `other` / human review should not be used as a workaround for personalized WhatsApp follow-ups, because it does not represent an outbound-message proof;
- likely V1/V2 candidate: add a dedicated personalized follow-up action or owner-per-step model so Setter I or Closer can review the conversation and send a tailored message;
- follow-up actions need an explicit "do not do this action" path with mandatory note and a deliberate next step: skip to next flux step, stop the flux, program another action, or close the conversation.

## Recommendation

Do not add new major features before the live SchoolDrive validation.

Recommended order:

1. keep staging on the latest workflow code;
2. clean/rebuild staging data only if needed for readability;
3. validate the fresh Lead and Presubscription path end to end;
4. run `pre_cutover_check`;
5. validate the workflow with Laura on a small real scenario set;
6. then decide production cutover.
