import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DocsHubPage, { MarkdownRenderer } from "./DocsHubPage";

const mockResponse = (data) =>
  Promise.resolve({
    ok: true,
    json: async () => data,
  });

describe("DocsHubPage", () => {
  beforeEach(() => {
    global.fetch = jest.fn((url) => {
      if (url.includes("/api/v1/docs/") && !url.endsWith("/api/v1/docs")) {
        return mockResponse({
          slug: "getting-started",
          title: "Getting started",
          section: "Getting started",
          summary: "Quick start",
          headings: ["Create your first website"],
          content: "# Getting started\nHello world",
        });
      }
      if (url.includes("/api/v1/docs")) {
        return mockResponse([
          {
            slug: "getting-started",
            title: "Getting started",
            section: "Getting started",
            summary: "Quick start",
            headings: ["Create your first website"],
          },
          {
            slug: "install-agent",
            title: "Install the browser agent",
            section: "Install agent",
            summary: "Embed the snippet",
            headings: ["Quick install"],
          },
        ]);
      }
      return mockResponse([]);
    });
  });

  afterEach(() => {
    global.fetch.mockClear();
  });

  it("renders markdown safely without injecting scripts", () => {
    const { container } = render(
      <MarkdownRenderer markdown={'<script>alert("x")</script>'} />
    );
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText('<script>alert("x")</script>')).toBeInTheDocument();
  });

  it("search finds the install agent guide", async () => {
    render(<DocsHubPage />);
    const searchInput = await screen.findByPlaceholderText("Search docs...");
    await userEvent.type(searchInput, "install");
    await waitFor(() => {
      expect(screen.getByText("Install the browser agent")).toBeInTheDocument();
    });
  });
});
