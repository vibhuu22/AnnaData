"""Local owner dashboard with the production admin routes, without starting models.

Run from backend: .venv/Scripts/python -m uvicorn admin_server:app --host 127.0.0.1 --port 8766
"""
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name('.env'))
load_dotenv(Path(__file__).with_name('.env.admin'))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from psycopg_pool import ConnectionPool
import db
import config
import admin_api


@asynccontextmanager
async def lifespan(app):
    # No legacy schema migrations, farmer changes, Earth Engine or model calls.
    db._pool=ConnectionPool(config.DATABASE_URL,min_size=0,max_size=3,timeout=20,
        kwargs={'connect_timeout':15},check=ConnectionPool.check_connection,open=True)
    try:
        yield
    finally:
        db.close()


app=FastAPI(title='AnnaData private analytics',lifespan=lifespan)
app.include_router(admin_api.router)
app.mount('/admin/assets',StaticFiles(directory=admin_api.WEB),name='admin-assets')


@app.middleware('http')
async def secure_responses(request,call_next):
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    return response
