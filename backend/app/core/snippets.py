from app.core.config import settings


def build_embed_snippet(public_key: str) -> str:
    agent_url = settings.AGENT_URL
    return (
        f'<script>window.__API_SHIELD_KEY__="{public_key}";</script>\n'
        f'<script async src="{agent_url}" data-key="{public_key}"></script>'
    )
