# Technical Debt And V2 Notes

This document tracks deliberate V1 shortcuts that must not be forgotten during staging and production cutover.

## Identity Resolution

### V1 Implemented Guardrail

Inbound WhatsApp matching is intentionally conservative:

- one exact phone match in Sales Cockpit: attach the message to that lead;
- zero exact matches: create a temporary `Inconnu(e)` lead marked `À identifier`;
- multiple exact matches: create a temporary `Inconnu(e)` lead marked `À identifier` and store the candidate leads for manual review.

Users can temporarily fill:

- first name;
- last name;
- course category;
- course/session;
- identification note.

The temporary data is operational only. It does not replace SchoolDrive as source of truth.

### V2 Debt

Sales Cockpit still needs a real identity-resolution workflow:

- search/replay SchoolDrive by phone, name, and email;
- merge a temporary Sales Cockpit lead into the correct SchoolDrive-backed lead;
- preserve and move the WhatsApp thread, messages, actions, events, notes, and Front history during merge;
- expose candidate selection in the UI for ambiguous matches;
- periodically retry matching temporary leads against newly created SchoolDrive records;
- decide whether Front unmatched conversations can create temporary identity records or stay in the Front buffer until matched.

### Cutover Risk

Do not auto-attach an inbound WhatsApp to a candidate when more than one lead shares the same phone number. Wrong identity attachment is more dangerous than a temporary `À identifier` record.

## Sequence Recalculation

### V1 Implemented Guardrail

Admins can tune active course categories, flux steps, and template mappings in Sales Cockpit. These changes deliberately affect only future flux actions created after the save.

Existing open tasks keep their original due date, step index, assignee, and recommended template. This avoids silently changing work already visible in a user's queue.

Flux steps are now stored as absolute offsets from the flow trigger (`offset_direction`, `offset_amount`, `offset_unit`). Recalculation must therefore use the original sequence anchor stored on tasks as `metadata_json.sequence_anchor_at`; it must not chain from the previous task's completion time.

### V2 Debt

Add a controlled recalculation workflow:

- preview which open or future tasks would change;
- show old versus new due date, step, template and assignee;
- let an admin apply the recalculation only to selected fluxes, categories, or leads;
- write an audit log entry for every recalculated task;
- never recalculate completed, cancelled, archived, signed, non pertinent, or do-not-contact conversations.

## Unsupported Course Categories

### V1 Implemented Guardrail

If SchoolDrive sends a lead or presubscription for a category not active in `course_categories`, Sales Cockpit stores the conversation and SchoolDrive WhatsApp messages, but creates a Setter I review task instead of starting the structured Tanjona follow-up flux.

### V2 Debt

Add a guided admin workflow to activate a new course category:

- choose or create the category;
- configure the default session;
- define templates for every required flow step;
- run a simulator before activation;
- optionally reprocess the waiting review tasks once the category is configured.

## Course-Start Follow-Up Engine

### V1 Implemented Guardrail

Course-start follow-ups can now be created from the SchoolDrive `course.start_date` or from the active default session date for the course category.

Runtime behavior:

- if a setting/closing call is already planned, the course-start follow-up does not interrupt it;
- if a course-start follow-up conflicts with a lead/presubscription follow-up within 24h, the course-start follow-up wins and the lead-relative follow-up is cancelled;
- if a category has no active default session and SchoolDrive provides no `start_date`, no course-start follow-up is created.

### V2 Debt

Add a global scheduling/recalculation workflow:

- periodic sweep that detects upcoming course-start reminders even when no fresh SchoolDrive event arrives;
- preview and recalculate affected future tasks after Laura changes default sessions, course-start flux steps, or template mappings;
- explain conflicts before applying changes;
- preserve planned setting/closing calls as non-interruptible actions;
- write audit logs for every cancelled/replaced task.
