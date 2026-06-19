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
