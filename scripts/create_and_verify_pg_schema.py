import os
import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import make_url

# Ensure project root is on sys.path so `backend` is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Use the app's models
from Backends.backend import models

url = os.getenv('DATABASE_URL')
if not url:
    print('ERROR: DATABASE_URL not set in environment for this process')
    sys.exit(2)

print('Using DATABASE_URL from env (masked)')
try:
    url_obj = make_url(url)
    print(f'Connecting to database: {url_obj.database} on {url_obj.host}:{url_obj.port} (driver: {url_obj.drivername})')
except Exception:
    print('Unable to parse DATABASE_URL')

engine = create_engine(url)

# Create tables without dropping anything
print('Calling Base.metadata.create_all(bind=engine) ...')
models.Base.metadata.create_all(bind=engine)
print('create_all completed')

inspector = inspect(engine)

tables = inspector.get_table_names()
print('\nDetected tables:')
for t in tables:
    print(' -', t)

# Verify specific tables and their columns
expected_tables = sorted(models.Base.metadata.tables.keys())
print('\nModel-declared tables:')
for t in expected_tables:
    print(' *', t)

print('\nInspecting columns and counts for model tables:')
for t in expected_tables:
    print('\nTable:', t)
    if t not in tables:
        print('  -> Table not present in database')
        continue
    cols = inspector.get_columns(t)
    print('  Columns:')
    for c in cols:
        print('   -', c['name'], c.get('type'))
    # safe count
    try:
        with engine.connect() as conn:
            r = conn.execute(text(f'SELECT COUNT(*) FROM "{t}"'))
            cnt = r.scalar()
    except Exception as e:
        cnt = f'ERROR: {e}'
    print('  Row count:', cnt)

print('\nDone')
