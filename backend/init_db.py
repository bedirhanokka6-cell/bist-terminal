from sqlalchemy import text
from app.db import Base, engine
from app import models  # noqa: F401


def main():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    Base.metadata.create_all(bind=engine)
    print("OK: PostgreSQL bağlantısı başarılı.")
    print("OK: Tablolar oluşturuldu: signals, watchlist, virtual_portfolio, signal_results")


if __name__ == "__main__":
    main()
