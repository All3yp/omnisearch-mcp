from omnisearch_mcp.config import Config, get_config


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("CONTACT_EMAIL", "test@domain.com")
    monkeypatch.setenv("SCITE_COOKIES", "test_scite_cookie")
    monkeypatch.setenv("CONSENSUS_COOKIES", "test_consensus_cookie")
    monkeypatch.setenv("IEEE_XPLORE_API_KEY", "ieee_key")
    monkeypatch.setenv("CORE_API_KEY", "core_key")

    cfg = Config.from_env()
    assert cfg.contact_email == "test@domain.com"
    assert "test@domain.com" in cfg.user_agent
    assert cfg.scite_cookies == "test_scite_cookie"
    assert cfg.consensus_cookies == "test_consensus_cookie"
    assert cfg.ieee_api_key == "ieee_key"
    assert cfg.core_api_key == "core_key"


def test_get_config_function():
    cfg = get_config()
    assert isinstance(cfg, Config)
    assert cfg.user_agent is not None
