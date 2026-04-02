import asyncio
import sys
import os

# Add the apps/api directory to the path
sys.path.append(os.path.join(os.getcwd(), "apps/api"))

from app.db import engine, Base
from app.models.projects import Project, AssessmentRun, KnowledgeChunk
from sqlalchemy import text

async def init_db():
    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        
        # Drop and recreate for a clean start in this sprint
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("Database initialized successfully.")

if __name__ == "__main__":
    asyncio.run(init_db())
