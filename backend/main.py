from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import scanner, chain, positions, market, earnings

app = FastAPI(title="Option Strategy API v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 启动时初始化数据库
init_db()

# 挂载所有路由
app.include_router(scanner.router)
app.include_router(chain.router)
app.include_router(positions.router)
app.include_router(market.router)
app.include_router(earnings.router)


@app.get("/")
def root():
    return {"status": "ok", "version": "2.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
