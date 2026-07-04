import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import scanner, chain, positions, market, earnings, news, portfolio, analytics
from routers import vol, spreads, payoff, risk
from services import cache as cache_svc
from services import warmup
from services.vol import init_iv_history

_start_time = time.time()

app = FastAPI(title="Option Strategy API v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
init_iv_history()
warmup.start()

app.include_router(scanner.router)
app.include_router(chain.router)
app.include_router(positions.router)
app.include_router(market.router)
app.include_router(earnings.router)
app.include_router(news.router)
app.include_router(portfolio.router)
app.include_router(analytics.router)
app.include_router(vol.router)
app.include_router(spreads.router)
app.include_router(payoff.router)
app.include_router(risk.router)


@app.get("/")
def root():
    return {"status": "ok", "version": "2.0"}


@app.api_route("/api/health", methods=["GET", "HEAD"])
def health():
    return {
        "status": "ok",
        "uptime_s": round(time.time() - _start_time),
        "cache_keys": list(cache_svc._store.keys()),
    }


if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=False)
