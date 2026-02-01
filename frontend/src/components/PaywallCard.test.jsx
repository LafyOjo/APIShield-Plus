import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PaywallCard from "./PaywallCard";
import { apiFetch } from "../api";

jest.mock("../api", () => ({
  apiFetch: jest.fn(),
}));

const buildResponse = (data) =>
  Promise.resolve({
    ok: true,
    status: 200,
    json: async () => data,
  });

beforeEach(() => {
  apiFetch.mockReset();
  Object.defineProperty(window, "location", {
    value: { assign: jest.fn() },
    writable: true,
    configurable: true,
  });
});

test("test_upgrade_cta_launches_checkout_session", async () => {
  apiFetch.mockImplementation((path) => {
    if (path.startsWith("/api/v1/billing/checkout")) {
      return buildResponse({ checkout_url: "https://checkout.test/session" });
    }
    if (path.startsWith("/api/v1/onboarding/feature-locked")) {
      return buildResponse({ ok: true });
    }
    return buildResponse({});
  });

  const user = userEvent.setup();
  render(
    <PaywallCard
      title="Unlock Pro"
      featureKey="geo_map"
      source="test"
      planKey="pro"
    />
  );

  const button = screen.getByRole("button", { name: /upgrade/i });
  await user.click(button);

  expect(apiFetch).toHaveBeenCalledWith(
    "/api/v1/billing/checkout",
    expect.objectContaining({ method: "POST" })
  );
  expect(window.location.assign).toHaveBeenCalledWith(
    "https://checkout.test/session"
  );
});
