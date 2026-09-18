import os

# Point the app at an in-memory database before any app module is imported.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SEED_ON_EMPTY", "false")
