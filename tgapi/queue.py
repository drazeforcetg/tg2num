import asyncio
import time
import uuid
from typing import Dict, Any
from loguru import logger
from .telegramClient import queryBot
from .config import getSettings

_requestQueue: asyncio.Queue = asyncio.Queue()
_workerTasks: list = []
_activeWorkers: int = 0
_totalProcessed: int = 0

class WorkerPool:
    def __init__(self):
        self.workerCount = 0
        self.tasks = []

    async def start(self):
        settings = getSettings()
        self.workerCount = settings.workerCount
        for i in range(self.workerCount):
            task = asyncio.create_task(self._worker(f"worker-{i}"))
            self.tasks.append(task)
        logger.info(f"Started {self.workerCount} workers")

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def _worker(self, workerId: str):
        global _activeWorkers, _totalProcessed
        while True:
            try:
                job: Dict[str, Any] = await _requestQueue.get()
                _activeWorkers += 1
                try:
                    await self._processJob(job, workerId)
                finally:
                    _activeWorkers -= 1
                    _totalProcessed += 1
                    _requestQueue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {workerId} error: {e}")

    async def _processJob(self, job: Dict[str, Any], workerId: str):
        responseFuture: asyncio.Future = job["responseFuture"]
        query: str = job["query"]
        correlationId: str = job["correlationId"]
        settings = getSettings()

        try:
            result = await queryBot(query, correlationId, timeoutSec=settings.requestTimeoutSec)
            responseFuture.set_result({"result": result, "workerId": workerId})
        except Exception as e:
            if not responseFuture.done():
                responseFuture.set_exception(e)

async def enqueueRequest(query: str, correlationId: str) -> asyncio.Future:
    loop = asyncio.get_event_loop()
    responseFuture = loop.create_future()
    job = {
        "query": query,
        "correlationId": correlationId,
        "responseFuture": responseFuture,
        "enqueuedAt": time.monotonic(),
    }
    await _requestQueue.put(job)
    return responseFuture

def getQueueStats() -> Dict[str, Any]:
    return {
        "queueSize": _requestQueue.qsize(),
        "activeWorkers": _activeWorkers,
        "totalProcessed": _totalProcessed,
    }

workerPool = WorkerPool()