# Twilio WhatsApp Sender Strategy

## Current Situation

Sales Cockpit staging was first connected to Twilio Sandbox. This validated:

- inbound webhook handling;
- outbound free-form sending inside the sandbox session;
- status callbacks;
- Content API template synchronization.

It does not validate the final ESSR production sender.

François also validated a real DEV WhatsApp sender, `+41445054269`, under the legacy PMC / Permismoinscher context. That validation was useful historically, but the DEV WhatsApp account was later blocked by Meta. Do not rely on this sender for production validation.

Current safe posture: staging and production stay in Twilio `mock` mode until an explicit cutover decision. Sales Cockpit may synchronize real ESSR templates from Twilio Content API in read-only mode, but it must not change webhooks or send real WhatsApp messages before the cutover.

François confirmed that the ESSR WhatsApp number is already in use. Therefore, creating or buying an unrelated Twilio phone number does not solve the production template validation problem.

## Key Rule

For production WhatsApp under the ESSR brand, the relevant object is the WhatsApp sender: a phone number registered to a WhatsApp Business Account (WABA) and connected to a Twilio Account SID.

If the ESSR number is already attached to another provider, another WABA, another Twilio account, or WhatsApp Business App, it must be migrated or released before this Twilio account can use it as the production sender.

## Practical Consequence

Do not spend time trying to submit ESSR production templates from the current DEV setup unless the real ESSR WhatsApp sender/WABA path is clear. Meta may reject or block approval paths that are not attached to the right business sender context.

The useful tests already completed are:

- sandbox inbound/outbound mechanics;
- historical live DEV sender inbound/outbound mechanics with a strict recipient allowlist;
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

1. Keep staging and production in `mock` mode until explicit cutover.
2. Use staging to validate workflow, SchoolDrive integration, template synchronization, and UI behavior without real sends.
3. Clarify ESSR sender ownership and production WhatsApp routing before changing any webhook or sender configuration.
4. Once ownership is clear, create a small production cutover checklist.
5. Only then enable real sending/receiving on the ESSR production sender.

## References

- Twilio WhatsApp sender overview: https://www.twilio.com/docs/whatsapp
- Twilio self sign-up for WhatsApp senders: https://www.twilio.com/docs/whatsapp/self-sign-up
- Twilio migration of WhatsApp numbers and senders: https://www.twilio.com/docs/whatsapp/migrate-numbers-and-senders
- Twilio template approvals and statuses: https://www.twilio.com/docs/whatsapp/tutorial/message-template-approvals-statuses
- Twilio Content API templates: https://www.twilio.com/docs/content/content-api-resources
