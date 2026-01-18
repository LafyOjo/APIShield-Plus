import secrets


ALLOWED_VERIFICATION_METHODS = {
    "meta_tag",
    "well_known",
    "dns_txt",
}


def validate_verification_method(method: str) -> None:
    if method not in ALLOWED_VERIFICATION_METHODS:
        raise ValueError(f"Unsupported verification method: {method}")


def generate_verification_token() -> str:
    return f"dv_{secrets.token_urlsafe(24)}"


def build_verification_instructions(domain: str, token: str, method: str) -> str:
    validate_verification_method(method)
    if method == "meta_tag":
        return (
            "Add this meta tag to the <head> of your homepage: "
            f'<meta name="api-shield-verification" content="{token}">'
        )
    if method == "well_known":
        return (
            "Create a file at "
            f"https://{domain}/.well-known/api-shield-verification.txt "
            f"with the contents: {token}"
        )
    return (
        "Create a DNS TXT record for "
        f"_api-shield-verification.{domain} with the value: {token}"
    )
