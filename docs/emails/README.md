# Onboarding email templates

Templates are Markdown files with a simple front matter block:

```
---
subject: Example subject
preheader: Optional preheader text
cta_label: Button label
cta_url: {app_base_url}/path
cooldown_hours: 24
---
Body text with placeholders like {user_name} or {tenant_name}.
```

Supported placeholders:
- {user_name}
- {tenant_name}
- {app_base_url}
- {incident_id}
- {feature_name}
