"""
后台预热：进程存活期间定期把默认扫描结果灌进缓存，用户进来直接吃缓存（秒回），
不必等 ~115s 冷扫描。配合 keep-warm ping（保活不休眠），缓存就能持续保持新鲜。
"""
import logging
import threading
import time

logger = logging.getLogger("scanner")

# 与前端默认参数一致（ScannerTab：sell_put / 7 / 60 / 0 / 非宽松）
_DEFAULTS = dict(strategies="sell_put", dte_min=7, dte_max=60, min_iv_rank=0, relaxed=False)
_REFRESH_INTERVAL = 45 * 60  # < 缓存 1h TTL，保持新鲜
_INITIAL_DELAY = 5           # 让 app 先绑定端口、健康检查通过，再开扫
_started = False
_lock = threading.Lock()


def _warm_once():
    from routers.scanner import scan as scan_endpoint
    t = time.time()
    scan_endpoint(force_refresh=True, **_DEFAULTS)
    logger.info("[warmup] 默认扫描预热完成，耗时 %.1fs", time.time() - t)


def _loop():
    time.sleep(_INITIAL_DELAY)
    while True:
        try:
            _warm_once()
        except Exception as e:
            logger.warning("[warmup] 预热失败: %s", e)
        time.sleep(_REFRESH_INTERVAL)


def start():
    """启动后台预热线程（幂等）。"""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, daemon=True).start()
