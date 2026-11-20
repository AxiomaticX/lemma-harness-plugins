from lemma_mcp.config import TARGET


def test_the_plugin_talks_to_production_lemma():
    assert TARGET.api_url == "https://api.axiomatic-ai.com"
    assert TARGET.conversation_url("c1") == "https://lemma.axiomatic.ai/en/lemma/c1"
