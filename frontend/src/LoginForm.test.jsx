import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import LoginForm from "./LoginForm";
import { ACTIVE_TENANT_KEY, TOKEN_KEY, USERNAME_KEY, apiFetch, logAuditEvent } from "./api";

jest.mock("./api", () => ({
  apiFetch: jest.fn(),
  logAuditEvent: jest.fn(() => Promise.resolve()),
  API_BASE: "",
  ACTIVE_TENANT_KEY: "apiShieldActiveTenant",
  TOKEN_KEY: "apiShieldAuthToken",
  USERNAME_KEY: "apiShieldUsername",
}));

const makeResponse = (status, payload) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => payload,
  text: async () => (typeof payload === "string" ? payload : JSON.stringify(payload)),
});

beforeEach(() => {
  localStorage.clear();
  window.history.pushState({}, "", "/");
  apiFetch.mockReset();
  logAuditEvent.mockClear();

  apiFetch.mockImplementation((path) => {
    if (path === "/register") {
      return Promise.resolve(
        makeResponse(200, {
          id: 11,
          username: "newuser",
          role: "user",
          active_tenant_id: 22,
          active_tenant_slug: "newuser-workspace",
        })
      );
    }
    if (path === "/login") {
      return Promise.resolve(
        makeResponse(200, {
          access_token: "test-token",
          token_type: "bearer",
        })
      );
    }
    return Promise.resolve(makeResponse(200, {}));
  });
});

test("signup registers, auto-logins, and redirects to onboarding", async () => {
  const onLogin = jest.fn();
  render(<LoginForm onLogin={onLogin} />);

  fireEvent.click(screen.getByRole("button", { name: "Sign up" }));

  fireEvent.change(screen.getByLabelText("Username"), {
    target: { value: "newuser" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "hunter22" },
  });
  fireEvent.change(screen.getByLabelText("Confirm password"), {
    target: { value: "hunter22" },
  });

  fireEvent.click(screen.getByRole("button", { name: "Create account" }));

  await waitFor(() => {
    expect(apiFetch).toHaveBeenCalledWith(
      "/register",
      expect.objectContaining({ method: "POST" })
    );
  });

  await waitFor(() => {
    expect(apiFetch).toHaveBeenCalledWith(
      "/login",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-Tenant-ID": "newuser-workspace" }),
      })
    );
  });

  expect(localStorage.getItem(TOKEN_KEY)).toBe("test-token");
  expect(localStorage.getItem(USERNAME_KEY)).toBe("newuser");
  expect(localStorage.getItem(ACTIVE_TENANT_KEY)).toBe("newuser-workspace");
  expect(window.location.pathname).toBe("/dashboard/onboarding");
  expect(onLogin).toHaveBeenCalledWith("test-token");
  expect(logAuditEvent).toHaveBeenCalledWith("user_register", "newuser");
});
