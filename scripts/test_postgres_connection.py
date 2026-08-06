import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

url = os.getenv('DATABASE_URL')
if not url:
    print('ERROR: DATABASE_URL not set in environment for this process')
    raise SystemExit(2)

try:
    engine = create_engine(url)
    with engine.connect() as conn:
        r = conn.execute(text('SELECT 1'))
        val = r.scalar()
        url_obj = make_url(url)
        dbname = url_obj.database
        host = url_obj.host
        port = url_obj.port
        driver = url_obj.drivername
        print('PostgreSQL connection successful')
        print('SELECT 1 result:', val)
        print(f'Connected to database: {dbname} on {host}:{port}')
        print('Driver used:', driver)
except Exception as e:
    print('Connection failed:', repr(e))
    raise
