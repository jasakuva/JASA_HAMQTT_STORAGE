from types import SimpleNamespace

from hamqtt_store.auth import password_matches, set_password, valid_credentials


def test_credentials_require_username_and_six_character_password():
    assert valid_credentials("admin", "secret")
    assert not valid_credentials("", "secret")
    assert not valid_credentials("admin", "short")


def test_password_is_hashed_and_can_be_verified():
    user = SimpleNamespace(password_hash="", session_version=1)
    set_password(user, "secret")
    assert user.password_hash != "secret"
    assert password_matches(user, "secret")
    assert not password_matches(user, "wrong")
    assert user.session_version == 2


def test_password_initialization_handles_unset_session_version():
    user = SimpleNamespace(password_hash="", session_version=None)
    set_password(user, "secret")
    assert user.session_version == 1