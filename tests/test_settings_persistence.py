"""
Tests para SettingsPersistence — Abstracción de persistencia.
"""
from unittest.mock import patch

from services.settings_persistence import EnvSettingsPersistence


def test_save_sensitive():
    persistence = EnvSettingsPersistence()
    with patch("services.env_service.EnvService") as mock_env:
        persistence.save_sensitive("key123", "secret456")
        mock_env.save_sensitive.assert_called_once_with("key123", "secret456")


def test_rollback():
    persistence = EnvSettingsPersistence()
    snapshot = {"BINANCE_API_KEY": "old", "BINANCE_API_SECRET": "old_secret"}
    with patch("services.env_service.EnvService") as mock_env:
        persistence.rollback(snapshot)
        mock_env.rollback.assert_called_once_with(snapshot)
