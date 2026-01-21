import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SecurityMapPage from "./SecurityMapPage";
import { apiFetch, ACTIVE_TENANT_KEY } from "./api";

jest.mock("./GeoMapView", () => () => <div data-testid="geo-map" />);
jest.mock("./api", () => ({
  apiFetch: jest.fn(),
  ACTIVE_TENANT_KEY: "apiShieldActiveTenant",
}));

const buildResponse = (data) =>
  Promise.resolve({
    ok: true,
    status: 200,
    json: async () => data,
  });

const mockApiFetch = ({
  geoHistoryDays = 30,
  geoGranularity = "asn",
  geoFeatureEnabled = true,
  summaryItems = [],
  drilldownData = null,
} = {}) => {
  apiFetch.mockImplementation((path) => {
    if (path.startsWith("/api/v1/tenants")) {
      return buildResponse([{ id: 1, slug: "acme", name: "Acme Co" }]);
    }
    if (path.startsWith("/api/v1/websites/") && path.endsWith("/install")) {
      return buildResponse({ environments: [{ id: 3, name: "Prod" }] });
    }
    if (path.startsWith("/api/v1/websites")) {
      return buildResponse([
        { id: 2, display_name: "Acme Site", domain: "acme.test" },
      ]);
    }
    if (path.startsWith("/api/v1/map/summary")) {
      return buildResponse({ items: summaryItems });
    }
    if (path.startsWith("/api/v1/map/drilldown")) {
      return buildResponse(
        drilldownData || {
          countries: [],
          cities: [],
          asns: [],
          ip_hashes: [],
          paths: [],
        }
      );
    }
    if (path.startsWith("/api/v1/me")) {
      return buildResponse({
        entitlements: {
          limits: {
            geo_history_days: geoHistoryDays,
            geo_granularity: geoGranularity,
          },
          features: { geo_map: geoFeatureEnabled },
        },
      });
    }
    return buildResponse({});
  });
};

beforeEach(() => {
  localStorage.clear();
  apiFetch.mockReset();
  window.history.pushState({}, "", "/dashboard/security/map");
});

test("test_map_parses_filters_from_url()", async () => {
  const now = new Date();
  const from = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
  const to = new Date(now.getTime()).toISOString();
  window.history.pushState(
    {},
    "",
    `/dashboard/security/map?from=${encodeURIComponent(from)}&to=${encodeURIComponent(
      to
    )}&website_id=2&env_id=3&category=threat&severity=high`
  );
  localStorage.setItem(ACTIVE_TENANT_KEY, "acme");
  mockApiFetch();

  render(<SecurityMapPage />);

  await waitFor(() => {
    expect(screen.getByRole("option", { name: "Last 24 hours" }).selected).toBe(
      true
    );
    expect(screen.getByRole("option", { name: "Acme Site" }).selected).toBe(true);
    expect(screen.getByRole("option", { name: "Prod" }).selected).toBe(true);
    expect(screen.getByRole("option", { name: "Threats" }).selected).toBe(true);
    expect(screen.getByRole("option", { name: "High" }).selected).toBe(true);
  });
});

test("test_map_updates_url_on_filter_change()", async () => {
  localStorage.setItem(ACTIVE_TENANT_KEY, "acme");
  mockApiFetch();
  render(<SecurityMapPage />);

  const user = userEvent.setup();
  const categoryOption = await screen.findByRole("option", { name: "Threats" });
  const categorySelect = categoryOption.closest("select");
  await user.selectOptions(categorySelect, "threat");

  await waitFor(() => {
    const params = new URLSearchParams(window.location.search);
    expect(params.get("category")).toBe("threat");
    expect(params.get("from")).toBeTruthy();
    expect(params.get("to")).toBeTruthy();
  });
});

test("test_geo_map_ui_clamps_time_range_to_limit()", async () => {
  const now = new Date();
  const from = new Date(now.getTime() - 10 * 24 * 60 * 60 * 1000);
  const to = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  window.history.pushState(
    {},
    "",
    `/dashboard/security/map?from=${encodeURIComponent(
      from.toISOString()
    )}&to=${encodeURIComponent(to.toISOString())}&category=login`
  );
  localStorage.setItem(ACTIVE_TENANT_KEY, "acme");
  mockApiFetch({ geoHistoryDays: 2 });

  render(<SecurityMapPage />);

  await screen.findByText(/Time range limited to last 2 days/i);

  await waitFor(() => {
    const params = new URLSearchParams(window.location.search);
    const nextFrom = new Date(params.get("from"));
    const nextTo = new Date(params.get("to"));
    expect(nextFrom.getTime()).toBeGreaterThan(from.getTime());
    expect(nextTo.getTime() - nextFrom.getTime()).toBeLessThanOrEqual(
      2 * 24 * 60 * 60 * 1000 + 1000
    );
  });
});

test("test_geo_map_ui_hides_asn_when_not_entitled()", async () => {
  localStorage.setItem(ACTIVE_TENANT_KEY, "acme");
  mockApiFetch({
    geoGranularity: "country",
    summaryItems: [{ count: 12, country_code: "US" }],
    drilldownData: {
      countries: [{ country_code: "US", count: 12 }],
      cities: [],
      asns: [],
      ip_hashes: [],
      paths: [],
    },
  });

  render(<SecurityMapPage />);

  const user = userEvent.setup();
  const drillButton = await screen.findByRole("button", { name: /drilldown/i });
  await user.click(drillButton);

  expect(
    await screen.findByText(/Upgrade to see ASN-level attribution/i)
  ).toBeInTheDocument();
});

test("test_geo_map_ui_shows_upgrade_cta_when_feature_disabled()", async () => {
  localStorage.setItem(ACTIVE_TENANT_KEY, "acme");
  mockApiFetch({ geoFeatureEnabled: false });

  render(<SecurityMapPage />);

  expect(
    await screen.findByText(/Geo Map is a Pro feature/i)
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /upgrade/i })).toBeInTheDocument();
});
