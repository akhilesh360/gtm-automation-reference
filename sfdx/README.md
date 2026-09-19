# Salesforce metadata (optional)

Deployable SFDX source for the custom objects, fields, permission set, custom setting and the two orchestration-only Flows.
The local run does not need any of this. Deploy it when you want `SF_ENABLED=true` to write into a real Developer Org.

```bash
sf org login web -a gtm-dev
sf project deploy start -d force-app -o gtm-dev
sf org assign permset -n GTM_Automation -o gtm-dev
```

Then set the RevOps test mailbox: Setup -> Custom Settings -> GTM Settings -> Manage -> New (org default) -> RevOps Notification Email.

See `docs/salesforce_setup.md` for the full walkthrough and what each Flow does (and deliberately does not do).
