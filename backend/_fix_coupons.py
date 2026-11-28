from sqlalchemy import text
from database import engine, init_db

with engine.begin() as c:
    c.execute(text("DROP TABLE IF EXISTS user_coupons"))
init_db()
print("user_coupons ready")
