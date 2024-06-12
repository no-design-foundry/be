import pytest

from app import app as app_runner


@pytest.fixture()
def app():
    app_runner.config.update(
        {
            "TESTING": True,
        }
    )

    # other setup can go here

    yield app_runner

    # clean up / reset resources here


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def runner(app):
    return app.test_cli_runner()
