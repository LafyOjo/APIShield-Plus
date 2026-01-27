from pydantic import BaseModel


class DocMeta(BaseModel):
    slug: str
    title: str
    section: str
    summary: str | None = None
    headings: list[str] = []


class DocDetail(DocMeta):
    content: str
