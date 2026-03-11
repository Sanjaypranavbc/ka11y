#!/usr/bin/env python3

from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from ka11y.config.logger import setup_logger
from ka11y.utils.config_loader import load_config
from ka11y.api.router import router

logger = setup_logger(name="KAC", tag="main")
logger.info("Logger initialized")
config = load_config()
logger.info("Configuration loaded successfully")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ka11y API starting up")
    yield
    logger.info("ka11y API shutting down")


app = FastAPI(
    title="ka11y",
    description="AI Based Web Accessibility Checker",
    version="0.0.1",
    lifespan=lifespan
)

app.include_router(router)