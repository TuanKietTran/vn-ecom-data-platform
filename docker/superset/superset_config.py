import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = os.environ["SUPERSET_DB_URI"]
FEATURE_FLAGS = {"DASHBOARD_NATIVE_FILTERS": True}
BABEL_DEFAULT_LOCALE = "en"
LANGUAGES = {"en": {"flag": "us", "name": "English"}, "vi": {"flag": "vn", "name": "Tiếng Việt"}}
