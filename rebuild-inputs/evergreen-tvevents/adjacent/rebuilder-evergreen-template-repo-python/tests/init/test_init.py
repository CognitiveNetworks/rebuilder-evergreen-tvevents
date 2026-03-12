import logging
from fastapi import FastAPI
import app


def test_create_app_env():
    """
    Test that the app bootstraps correctly.
    """
    app_obj = app.create_app()
    assert isinstance(app_obj, FastAPI)


def test_odd_log_level():
    """
    Test that when passed a string that starts with Level, logging level gets set to debug.
    """
    level = app.compute_valid_log_level("Level Debug")
    assert level == logging.DEBUG
