from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import scanner, chain, positions, market, earnings, news

app = FastAPI(title="Option Strategy API v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

app.include_router(scanner.router)
app.include_router(chain.router)
app.include_router(positions.router)
app.include_router(market.router)
app.include_router(earnings.router)
app.include_router(news.router)


@app.get("/")
def root():
    return {"status": "ok", "version": "2.0"}


if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=False)
