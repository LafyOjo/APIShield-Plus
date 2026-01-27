import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, ACTIVE_TENANT_KEY } from "./api";

const escapeInline = (value) => String(value || "");

const tokenizeInline = (text) => {
  const tokens = [];
  let cursor = 0;
  while (cursor < text.length) {
    const nextCode = text.indexOf("`", cursor);
    const nextLink = text.indexOf("[", cursor);
    const nextSpecial = [nextCode, nextLink].filter((idx) => idx >= 0).sort((a, b) => a - b)[0];
    if (nextSpecial == null) {
      tokens.push({ type: "text", value: text.slice(cursor) });
      break;
    }
    if (nextSpecial > cursor) {
      tokens.push({ type: "text", value: text.slice(cursor, nextSpecial) });
    }
    if (nextSpecial === nextCode) {
      const end = text.indexOf("`", nextCode + 1);
      if (end > nextCode) {
        tokens.push({ type: "code", value: text.slice(nextCode + 1, end) });
        cursor = end + 1;
        continue;
      }
    }
    if (nextSpecial === nextLink) {
      const closeBracket = text.indexOf("]", nextLink + 1);
      const openParen = closeBracket >= 0 ? text.indexOf("(", closeBracket) : -1;
      const closeParen = openParen >= 0 ? text.indexOf(")", openParen) : -1;
      if (closeBracket > nextLink && openParen === closeBracket + 1 && closeParen > openParen) {
        const label = text.slice(nextLink + 1, closeBracket);
        const href = text.slice(openParen + 1, closeParen);
        tokens.push({ type: "link", label, href });
        cursor = closeParen + 1;
        continue;
      }
    }
    tokens.push({ type: "text", value: text.slice(nextSpecial, nextSpecial + 1) });
    cursor = nextSpecial + 1;
  }
  return tokens;
};

const InlineText = ({ text }) => {
  const tokens = tokenizeInline(text || "");
  return tokens.map((token, idx) => {
    if (token.type === "code") {
      return (
        <code key={`code-${idx}`} className="inline-code">
          {escapeInline(token.value)}
        </code>
      );
    }
    if (token.type === "link") {
      const href = token.href || "#";
      const safeHref = href.startsWith("http") || href.startsWith("/") || href.startsWith("#")
        ? href
        : "#";
      return (
        <a key={`link-${idx}`} href={safeHref} rel="noreferrer" target={safeHref.startsWith("http") ? "_blank" : "_self"}>
          {escapeInline(token.label)}
        </a>
      );
    }
    return <span key={`text-${idx}`}>{escapeInline(token.value)}</span>;
  });
};

const CodeBlock = ({ code, language }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(code);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }
    } catch (err) {
      // swallow copy errors
    }
  }, [code]);

  return (
    <div className="doc-code-block">
      <div className="doc-code-header">
        <span className="doc-code-lang">{language || "code"}</span>
        <button className="btn secondary small" onClick={handleCopy}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
};

const parseMarkdown = (markdown) => {
  const lines = (markdown || "").split(/\r?\n/);
  const blocks = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (line.trim().startsWith("```")) {
      const language = line.trim().slice(3).trim();
      const codeLines = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      blocks.push({ type: "code", language, value: codeLines.join("\n") });
      index += 1;
      continue;
    }
    if (/^#{1,6}\s/.test(line)) {
      const level = line.match(/^#{1,6}/)[0].length;
      blocks.push({ type: "heading", level, value: line.replace(/^#{1,6}\s*/, "") });
      index += 1;
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^[-*]\s+/, ""));
        index += 1;
      }
      blocks.push({ type: "list", items });
      continue;
    }
    if (!line.trim()) {
      index += 1;
      continue;
    }
    const paragraphLines = [line.trim()];
    index += 1;
    while (index < lines.length && lines[index].trim() && !/^#{1,6}\s/.test(lines[index]) && !lines[index].trim().startsWith("```") && !/^[-*]\s+/.test(lines[index])) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ type: "paragraph", value: paragraphLines.join(" ") });
  }
  return blocks;
};

export const MarkdownRenderer = ({ markdown }) => {
  const blocks = useMemo(() => parseMarkdown(markdown), [markdown]);
  return (
    <div className="docs-markdown">
      {blocks.map((block, idx) => {
        if (block.type === "heading") {
          const Tag = `h${Math.min(block.level + 1, 4)}`;
          return (
            <Tag key={`heading-${idx}`}>
              <InlineText text={block.value} />
            </Tag>
          );
        }
        if (block.type === "paragraph") {
          return (
            <p key={`para-${idx}`}>
              <InlineText text={block.value} />
            </p>
          );
        }
        if (block.type === "list") {
          return (
            <ul key={`list-${idx}`}>
              {block.items.map((item, itemIdx) => (
                <li key={`list-${idx}-${itemIdx}`}>
                  <InlineText text={item} />
                </li>
              ))}
            </ul>
          );
        }
        if (block.type === "code") {
          return (
            <CodeBlock key={`code-${idx}`} code={block.value} language={block.language} />
          );
        }
        return null;
      })}
    </div>
  );
};

const normalizeSearch = (value) => String(value || "").toLowerCase();

export default function DocsHubPage() {
  const [docs, setDocs] = useState([]);
  const [selectedSlug, setSelectedSlug] = useState("");
  const [docContent, setDocContent] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [snippet, setSnippet] = useState("");
  const [websites, setWebsites] = useState([]);
  const [selectedWebsiteId, setSelectedWebsiteId] = useState("");
  const activeTenant = localStorage.getItem(ACTIVE_TENANT_KEY) || "";

  const loadDocs = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const resp = await apiFetch("/api/v1/docs");
      if (!resp.ok) throw new Error("Unable to load docs");
      const data = await resp.json();
      setDocs(data || []);
      if (!selectedSlug && data?.length) {
        const params = new URLSearchParams(window.location.search);
        const initial = params.get("doc");
        const fallback = data[0].slug;
        const nextSlug = initial && data.some((doc) => doc.slug === initial) ? initial : fallback;
        setSelectedSlug(nextSlug);
      }
    } catch (err) {
      setError(err.message || "Unable to load docs");
    } finally {
      setLoading(false);
    }
  }, [selectedSlug]);

  const loadDoc = useCallback(async (slug) => {
    if (!slug) return;
    setLoading(true);
    setError("");
    try {
      const resp = await apiFetch(`/api/v1/docs/${slug}`);
      if (!resp.ok) throw new Error("Unable to load doc");
      const data = await resp.json();
      setDocContent(data?.content || "");
    } catch (err) {
      setError(err.message || "Unable to load doc");
      setDocContent("");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadWebsites = useCallback(async () => {
    if (!activeTenant) return;
    try {
      const resp = await apiFetch("/api/v1/websites");
      if (!resp.ok) throw new Error("Unable to load websites");
      const data = await resp.json();
      setWebsites(data || []);
      if (data?.length && !selectedWebsiteId) {
        setSelectedWebsiteId(String(data[0].id));
      }
    } catch (err) {
      setWebsites([]);
    }
  }, [activeTenant, selectedWebsiteId]);

  const loadSnippet = useCallback(async () => {
    if (selectedSlug !== "install-agent") return;
    if (!selectedWebsiteId) {
      setSnippet("");
      return;
    }
    try {
      const resp = await apiFetch(`/api/v1/websites/${selectedWebsiteId}/install`);
      if (!resp.ok) throw new Error("Unable to load install info");
      const data = await resp.json();
      const env = data?.environments?.[0];
      const key = env?.keys?.[0];
      setSnippet(key?.snippet || "");
    } catch (err) {
      setSnippet("");
    }
  }, [selectedSlug, selectedWebsiteId]);

  useEffect(() => {
    loadDocs();
  }, [loadDocs]);

  useEffect(() => {
    if (selectedSlug) {
      loadDoc(selectedSlug);
    }
  }, [selectedSlug, loadDoc]);

  useEffect(() => {
    if (selectedSlug === "install-agent") {
      loadWebsites();
    }
  }, [selectedSlug, loadWebsites]);

  useEffect(() => {
    loadSnippet();
  }, [loadSnippet]);

  useEffect(() => {
    if (!selectedSlug) return;
    const params = new URLSearchParams(window.location.search);
    params.set("doc", selectedSlug);
    const nextUrl = `${window.location.pathname}?${params.toString()}${window.location.hash || ""}`;
    window.history.replaceState({}, "", nextUrl);
  }, [selectedSlug]);

  const filteredDocs = useMemo(() => {
    const query = normalizeSearch(search);
    if (!query) return docs;
    return docs.filter((doc) => {
      const haystack = [
        doc.title,
        doc.summary,
        ...(doc.headings || []),
        doc.section,
      ]
        .filter(Boolean)
        .map(normalizeSearch)
        .join(" ");
      return haystack.includes(query);
    });
  }, [docs, search]);

  const docsBySection = useMemo(() => {
    const grouped = {};
    filteredDocs.forEach((doc) => {
      const section = doc.section || "General";
      if (!grouped[section]) grouped[section] = [];
      grouped[section].push(doc);
    });
    Object.values(grouped).forEach((items) => {
      items.sort((a, b) => a.title.localeCompare(b.title));
    });
    return grouped;
  }, [filteredDocs]);

  const selectedMeta = docs.find((doc) => doc.slug === selectedSlug);
  const resolvedContent = useMemo(() => {
    if (!docContent) return "";
    if (docContent.includes("{{AGENT_SNIPPET}}")) {
      const resolvedSnippet = snippet || "<script>/* Create a key to get your snippet */</script>";
      return docContent.replace("{{AGENT_SNIPPET}}", resolvedSnippet);
    }
    return docContent;
  }, [docContent, snippet]);

  return (
    <div className="stack docs-hub">
      <section className="card docs-header">
        <div>
          <h2 className="section-title">Help Center</h2>
          <p className="subtle">
            Install guides, troubleshooting steps, and verification playbooks.
          </p>
        </div>
        <div className="docs-search">
          <input
            type="search"
            placeholder="Search docs..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
      </section>

      <section className="docs-grid">
        <aside className="card docs-sidebar">
          {Object.keys(docsBySection).length === 0 && (
            <div className="subtle">No docs found.</div>
          )}
          {Object.entries(docsBySection).map(([section, items]) => (
            <div key={section} className="docs-section">
              <div className="docs-section-title">{section}</div>
              <div className="docs-section-list">
                {items.map((doc) => (
                  <button
                    key={doc.slug}
                    className={`docs-link ${selectedSlug === doc.slug ? "active" : ""}`}
                    onClick={() => setSelectedSlug(doc.slug)}
                  >
                    <span>{doc.title}</span>
                    {doc.summary && <span className="subtle">{doc.summary}</span>}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </aside>

        <div className="card docs-content">
          {loading && <div className="subtle">Loading documentation...</div>}
          {error && <div className="error-text">{error}</div>}
          {!loading && !error && selectedMeta && (
            <>
              <div className="docs-content-header">
                <div>
                  <h3 className="section-title">{selectedMeta.title}</h3>
                  {selectedMeta.summary && (
                    <p className="subtle">{selectedMeta.summary}</p>
                  )}
                </div>
                {selectedSlug === "install-agent" && (
                  <div className="docs-snippet-select">
                    <label className="label">Website</label>
                    <select
                      className="select"
                      value={selectedWebsiteId}
                      onChange={(event) => setSelectedWebsiteId(event.target.value)}
                    >
                      {websites.length === 0 && (
                        <option value="">Create a website first</option>
                      )}
                      {websites.map((site) => (
                        <option key={site.id} value={site.id}>
                          {site.display_name || site.domain}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
              <MarkdownRenderer markdown={resolvedContent} />
            </>
          )}
        </div>
      </section>
    </div>
  );
}
