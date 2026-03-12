from flask import Flask
import app


def test_create_app_env():
    app_obj = app.create_app()
    assert isinstance(app_obj, Flask)
    assert "routes" in app_obj.blueprints
