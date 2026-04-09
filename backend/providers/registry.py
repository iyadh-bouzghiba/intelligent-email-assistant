from backend.providers.gmail import GmailProvider

REGISTRY = {
    "gmail": GmailProvider,
}


def get_provider(name, supabase, security_manager):
    normalized_name = (name or "gmail").strip().lower()

    provider_cls = REGISTRY.get(normalized_name)
    if not provider_cls:
        raise ValueError(f"Unknown provider: {normalized_name}")

    return provider_cls(supabase=supabase, security_manager=security_manager)