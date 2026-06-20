# Twilio Sandbox Integration

## Scope

Sales Cockpit supports three Twilio modes:

- `mock`: default local/staging-safe mode. No Twilio API call is made.
- `sandbox`: real Twilio Sandbox API calls and signed webhooks.
- `live`: real Twilio sender API calls. Use this for a validated DEV WhatsApp sender before production cutover.

Do not switch production WhatsApp traffic to Sales Cockpit without an explicit cutover plan.

For the ESSR production sender and WABA migration questions, read:

```text
docs/TWILIO_SENDER_MIGRATION.md
```

## Staging URLs

Current staging API:

```text
http://139.59.158.77:8602
```

Configure Twilio Sandbox inbound messages to:

```text
http://139.59.158.77:8602/webhooks/twilio/whatsapp/inbound
```

Configure outbound message status callbacks to:

```text
http://139.59.158.77:8602/webhooks/twilio/whatsapp/status
```

Plain HTTP is acceptable only for sandbox testing. Production must use HTTPS.

## Required Environment Variables

For sandbox on staging:

```text
SALES_COCKPIT_TWILIO_MODE=sandbox
SALES_COCKPIT_TWILIO_ACCOUNT_SID=AC...
SALES_COCKPIT_TWILIO_AUTH_TOKEN=...
SALES_COCKPIT_TWILIO_WHATSAPP_SENDER=+14155238886
SALES_COCKPIT_TWILIO_MESSAGING_SERVICE_SID=
SALES_COCKPIT_TWILIO_ALLOWED_RECIPIENTS=
SALES_COCKPIT_TWILIO_VALIDATE_SIGNATURE=true
SALES_COCKPIT_TWILIO_WEBHOOK_URL=http://139.59.158.77:8602
SALES_COCKPIT_TWILIO_STATUS_CALLBACK_URL=http://139.59.158.77:8602/webhooks/twilio/whatsapp/status
```

Use either:

- `SALES_COCKPIT_TWILIO_WHATSAPP_SENDER` for the WhatsApp sender/sandbox number; or
- `SALES_COCKPIT_TWILIO_MESSAGING_SERVICE_SID` if Twilio is configured through a Messaging Service.

For Twilio Sandbox, the sender is usually the sandbox WhatsApp number shown in Twilio Console.

Historical DEV sender note. The former real DEV WhatsApp sender was later blocked by Meta, so do not rely on it for production validation. Keep this example only as a reminder of the allowlist pattern; read `docs/TWILIO_SENDER_MIGRATION.md` before using any real sender.

```text
SALES_COCKPIT_TWILIO_MODE=live
SALES_COCKPIT_TWILIO_WHATSAPP_SENDER=+41445054269
SALES_COCKPIT_TWILIO_ALLOWED_RECIPIENTS=+41762845576
```

Keep `SALES_COCKPIT_TWILIO_ALLOWED_RECIPIENTS` populated while staging contains real SchoolDrive prospects. This comma-separated allowlist prevents accidental outbound WhatsApp sends to real prospects during DEV sender validation. Remove or widen it only for an explicit cutover rehearsal.

## Implemented Behavior

Inbound webhook:

- accepts real Twilio `application/x-www-form-urlencoded` payloads;
- validates `X-Twilio-Signature` with the Twilio Auth Token;
- strips the `whatsapp:` prefix from `From`;
- stores the inbound message in `messages`;
- deduplicates by `MessageSid`;
- reopens the conversation and creates/updates a `reply` action for Setter 1;
- keeps the legacy JSON mock shape for internal tests only.

Status callback:

- validates the Twilio signature;
- updates `messages.twilio_status`, `twilio_error_code`, and `twilio_error_message`;
- logs a `twilio_message_status_updated` event;
- returns 200 even for an unknown `MessageSid`, so Twilio does not retry forever.

Outbound sending:

- uses mock mode by default;
- in `sandbox` or `live`, sends through Twilio's Python SDK;
- free-form messages use `Body`;
- templates use `ContentSid` and `ContentVariables`;
- `SALES_COCKPIT_TWILIO_STATUS_CALLBACK_URL` is passed as `StatusCallback` when configured.

Template management:

- admins can synchronize templates from Twilio Content API;
- admins can create a text template in Twilio from Sales Cockpit;
- admins can submit the new template for WhatsApp approval;
- non-admin users can browse templates and create template requests, but cannot create or synchronize Twilio templates.

Template audit:

```bash
python scripts/twilio_template_audit.py
```

To fail when no real approved Twilio template is available:

```bash
python scripts/twilio_template_audit.py --require-approved-real
```

Demo templates with `HX_MOCK_*` are deliberately excluded from the real approved-template count.

Delivery checks in the conversation thread:

- `...` means queued or sending;
- `✓` means sent;
- `✓✓` means delivered;
- blue `✓✓` means read;
- `!` means failed or undelivered.

## Important Template Constraint

When Twilio mode is `sandbox` or `live`, approved templates must have a real Twilio `twilio_content_sid`.

Demo templates with `HX_MOCK` are valid only in mock mode.

## Manual Sandbox Test

1. Put the staging env vars in `/opt/sales-cockpit/staging/.env`.
2. Redeploy or run `pip install -r requirements.txt` on the droplet.
3. Restart:

```bash
sudo systemctl restart sales-cockpit-api@staging
sudo systemctl restart sales-cockpit-ui@staging
```

4. In Twilio Console > WhatsApp Sandbox, set the inbound webhook URL.
5. Join the Twilio Sandbox from a phone.
6. Send a WhatsApp message to the sandbox.
7. Verify in Sales Cockpit that the conversation appears in Mihary's queue with a `Repondre au message` action.

## References

- Twilio webhook signature validation: https://www.twilio.com/docs/usage/webhooks/webhooks-security
- Twilio WhatsApp quickstart and sandbox setup: https://www.twilio.com/docs/whatsapp/quickstart
- Twilio Message resource: https://www.twilio.com/docs/messaging/api/message-resource
- Twilio Content Template sending: https://www.twilio.com/docs/content/send-templates-created-with-the-content-template-builder
