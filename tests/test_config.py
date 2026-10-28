from modules.database import config_db


def test_secret_masking():
    assert config_db.is_secret_key("render_api_key")
    assert config_db.is_secret_key("helper_bot_tokens")
    assert config_db.is_secret_key("render_deploy_hook_url")
    assert not config_db.is_secret_key("bot_title")
    assert config_db.mask_value("render_api_key", "rnd_abcdef1234") == "\u2022\u2022\u2022\u20221234"
    assert config_db.mask_value("bot_title", "My Bot") == "My Bot"
    assert config_db.mask_value("render_api_key", "") == ""


def test_no_hardcoded_secrets_in_defaults():
    for table in (config_db.DEFAULT_CONFIGS, config_db.EXTENDED_DEFAULT_CONFIGS):
        for key, (value, _t, _d) in table.items():
            if config_db.is_secret_key(key):
                assert value == "", key


def test_owner_ids_from_env(monkeypatch):
    from modules.database import user_db
    monkeypatch.setenv("ADMIN_IDS", "1, 2,x")
    monkeypatch.setenv("OWNER_IDS", "3")
    assert user_db.get_owner_ids() == {1, 2, 3}
