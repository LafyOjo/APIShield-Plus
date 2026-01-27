export const ROLE_TEMPLATES = [
  {
    value: "owner",
    label: "Owner",
    description: "Full control across workspace settings, billing, and security.",
  },
  {
    value: "admin",
    label: "Admin",
    description: "Manage workspace settings, security, and operational configuration.",
  },
  {
    value: "security_admin",
    label: "Security Admin",
    description: "Manage security workflows and diagnostics without billing access.",
  },
  {
    value: "billing_admin",
    label: "Billing Admin",
    description: "Manage subscriptions and billing without broader admin access.",
  },
  {
    value: "analyst",
    label: "Analyst",
    description: "Triage incidents, review threats, and apply prescriptions.",
  },
  {
    value: "viewer",
    label: "Viewer",
    description: "Read-only access to dashboards and reports.",
  },
];

export const getRoleTemplate = (roleValue) => {
  if (!roleValue) return null;
  const normalized = String(roleValue).toLowerCase();
  return ROLE_TEMPLATES.find((role) => role.value === normalized) || null;
};
