import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import DemoLabPage from "./DemoLabPage";
import { ACTIVE_TENANT_KEY, apiFetch } from "./api";

jest.mock("./api", () => ({
  apiFetch: jest.fn(),
  ACTIVE_TENANT_KEY: "apiShieldActiveTenant",
}));

const jsonResponse = (status, payload) => ({
  ok: status >= 200 && status < 300,
  status,
  headers: {
    get: (header) =>
      header && header.toLowerCase() === "content-type"
        ? "application/json"
        : null,
  },
  json: async () => payload,
  text: async () => JSON.stringify(payload),
});

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem(ACTIVE_TENANT_KEY, "acme");

  apiFetch.mockImplementation((path) => {
    if (path === "/api/v1/demo/seed") {
      return Promise.resolve(
        jsonResponse(201, {
          tenant_id: 1,
          counts: { behaviour_events: 42 },
        })
      );
    }
    if (path.startsWith("/api/v1/revenue/leaks")) {
      return Promise.resolve(
        jsonResponse(403, {
          detail: "Revenue leak estimates require a Pro plan",
        })
      );
    }
    if (path.startsWith("/api/v1/portfolio/summary")) {
      return Promise.resolve(
        jsonResponse(403, {
          detail: "Portfolio scorecards require a Business plan",
        })
      );
    }
    if (path.startsWith("/api/v1/admin/")) {
      return Promise.resolve(
        jsonResponse(403, {
          detail: "Platform admin required",
        })
      );
    }
    if (path.startsWith("/api/v1/map/summary")) {
      return Promise.resolve(jsonResponse(200, { items: [] }));
    }
    if (path.startsWith("/api/v1/trust/snapshots")) {
      return Promise.resolve(jsonResponse(200, []));
    }
    if (path.startsWith("/api/v1/tenants")) {
      return Promise.resolve(jsonResponse(200, [{ id: 1, slug: "acme", name: "Acme" }]));
    }
    if (path.startsWith("/api/v1/me")) {
      return Promise.resolve(jsonResponse(200, { user: { id: 1, email: "owner@acme.test" } }));
    }
    return Promise.resolve(jsonResponse(200, {}));
  });
});

afterEach(() => {
  apiFetch.mockReset();
});

test("demo lab runs checks and supports demo seed action", async () => {
  render(<DemoLabPage />);

  expect(await screen.findByText("Demo Lab")).toBeInTheDocument();

  await waitFor(() => {
    expect(apiFetch).toHaveBeenCalledWith("/api/v1/admin/queue/stats", {
      skipReauth: true,
    });
  });

  expect(screen.getAllByText(/ERROR \(403\)/i).length).toBeGreaterThan(0);

  apiFetch.mockClear();
  fireEvent.click(screen.getByRole("button", { name: "Seed demo data" }));

  await waitFor(() => {
    expect(apiFetch).toHaveBeenCalledWith(
      "/api/v1/demo/seed",
      expect.objectContaining({
        method: "POST",
      })
    );
  });

  expect(await screen.findByText(/Demo data seeded:/i)).toBeInTheDocument();
});
