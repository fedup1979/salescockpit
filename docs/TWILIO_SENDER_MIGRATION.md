# Twilio WhatsApp Sender Strategy

## Current Situation

Sales Cockpit staging was first connected to Twilio Sandbox. This validated:

- inbound webhook handling;
- outbound free-form sending inside the sandbox session;
- status callbacks;
- Content API template synchronization.

It does not validate the final ESSR production sender.

François has also validated a real DEV WhatsApp sender, `+41445054269`, under the legacy PMC / Permismoinscher context. Staging now uses this sender in `live` mode with a strict recipient allowlist. This can validate live Twilio sender mechanics in staging, but it is not the final ESSR production sender.

François confirmed that the ESSR WhatsApp number is already in use. Therefore, creating or buying an unrelated Twilio phone number does not solve the production template validation problem.

## Key Rule

For production WhatsApp under the ESSR brand, the relevant object is the WhatsApp sender: a phone number registered to a WhatsApp Business Account (WABA) and connected to a Twilio Account SID.

If the ESSR number is already attached to another provider, another WABA, another Twilio account, or WhatsApp Business App, it must be migrated or released before this Twilio account can use it as the production sender.

## Practical Consequence

Do not spend time trying to submit ESSR production templates from the current DEV setup unless the real ESSR WhatsApp sender/WABA path is clear. Meta may reject or block approval paths that are not attached to the right business sender context.

The current useful DEV tests are:

- sandbox inbound/outbound mechanics;
- live DEV sender inbound/outbound mechanics with a strict recipient allowlist;
- Content API synchronization;
- local UI template search and placeholder rendering;
- blocked/free-form rule behavior when the 24h window is closed.

The real production test requires:

- final Twilio Account SID selected;
- ESSR WABA / sender ownership clarified;
- ESSR WhatsApp number migrated or registered;
- real templates submitted and approved for that sender context;
- cutover plan with Front still available until validation passes.

## Migration Questions For Tiago / Twilio Admin

1. Where is the ESSR WhatsApp number currently registered?
2. Is it attached to WhatsApp Business App, Meta Cloud API, another BSP, Front/Twilio, or another Twilio account?
3. Which Meta Business Portfolio and WABA own it?
4. Who can approve migration or release of the number?
5. Should Sales Cockpit use the current Twilio account, a new Twilio production subaccount, or an existing ESSR Twilio account?
6. Do we need to migrate an existing WhatsApp sender from another Twilio account or migrate a phone number from another provider?

## Recommended Path

1. Keep staging on the real DEV sender with a strict recipient allowlist.
2. Use staging to validate workflow, SchoolDrive integration, and live DEV sender mechanics.
3. In parallel, clarify ESSR sender ownership.
4. Once ownership is clear, create a small production cutover checklist.
5. Only then submit ESSR production templates for Meta approval.

## References

- Twilio WhatsApp sender overview: https://www.twilio.com/docs/whatsapp
- Twilio self sign-up for WhatsApp senders: https://www.twilio.com/docs/whatsapp/self-sign-up
- Twilio migration of WhatsApp numbers and senders: https://www.twilio.com/docs/whatsapp/migrate-numbers-and-senders
- Twilio template approvals and statuses: https://www.twilio.com/docs/whatsapp/tutorial/message-template-approvals-statuses
- Twilio Content API templates: https://www.twilio.com/docs/content/content-api-resources
