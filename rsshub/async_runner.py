import asyncio
import threading

class AsyncRunner:
    """单例异步运行器，在后台线程中维护事件循环"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance
    
    def _init(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
    
    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
    
    def run(self, coro):
        """在后台事件循环中运行协程"""
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

async_runner = AsyncRunner()