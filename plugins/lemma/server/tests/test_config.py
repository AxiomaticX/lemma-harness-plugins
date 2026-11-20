import pytest

from lemma_mcp.config import target


@pytest.mark.parametrize(
    ("name", "api_url"),
    [
        (None, "https://api.axiomatic-ai.com"),
        ("", "https://api.axiomatic-ai.com"),
        ("production", "https://api.axiomatic-ai.com"),
        (" Staging ", "https://api.staging.axiomatic-ai.com"),
        ("STAGING.", "https://api.staging.axiomatic-ai.com"),
        ("dev", "https://api.dev.axiomatic-ai.com"),
    ],
)
def test_the_environment_named_or_production(name, api_url):
    assert target(name).api_url == api_url


def test_an_unknown_environment_is_refused():
    with pytest.raises(ValueError, match="production, staging, or dev"):
        target("local")
