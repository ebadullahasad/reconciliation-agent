from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

from app.database import Base, engine
from app.routers import reconcile, upload

Base.metadata.create_all(bind=engine)

app = FastAPI(title="ReconAgent")
app.include_router(upload.router)
app.include_router(reconcile.router)


@app.get("/health")
def health():
    return {"status": "ok"}
