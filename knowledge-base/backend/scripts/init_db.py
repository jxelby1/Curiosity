from app.core.config import get_settings
from app.db.init_db import init_db


def run() -> None:
    settings = get_settings()
    settings.validate_runtime_requirements()
    init_db()
    print('Database initialized successfully.')


if __name__ == '__main__':
    run()
