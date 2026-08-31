from ai_stp_platform.legal.builtin import builtin_policies
from ai_stp_platform.models import AccountPolicyAcceptance


def test_builtin_legal_policies_are_complete_and_versioned() -> None:
    policies = builtin_policies()
    assert {(policy.locale, policy.slug) for policy in policies} == {
        (locale, slug)
        for locale in ("en", "ru")
        for slug in (
            "service-rules",
            "privacy",
            "personal-data-consent",
            "cookies",
            "licensing",
        )
    }
    assert all(policy.policy_version and policy.effective_at for policy in policies)
    assert all(
        policy.source_path.startswith("docs-user-facing/legal/")
        for policy in policies
    )
    assert all(
        f"/{policy.slug}/{policy.policy_version}/document.md" in policy.source_path
        for policy in policies
    )
    assert all("admin@aiguild.space" in policy.markdown_source for policy in policies)
    assert all("{{" not in policy.markdown_source for policy in policies)
    assert {"ip", "source_ip", "user_agent", "provider_token"}.isdisjoint(
        AccountPolicyAcceptance.__table__.columns.keys()
    )
