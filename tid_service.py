"""
TID 服务 - 集成的 Twitter Transaction ID 获取服务
使用 patchright 浏览器捕获 Twitter 请求中的 x-client-transaction-id
"""
import asyncio
import time
import logging
import random
from urllib.parse import urlparse
from typing import Optional, List, Dict
from dataclasses import dataclass, field

# Setup logging
logger = logging.getLogger(__name__)

# TID 服务配置
TID_CONFIG = {
    "TWITTER_URL": "https://x.com/elonmusk",
    "USER_AGENT": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1 Edg/141.0.0.0",
    "REFRESH_INTERVAL": 10,  # 页面刷新间隔(秒)
    "HEADLESS": True,
}


@dataclass
class TIDService:
    """TID 服务单例类"""
    _instance: Optional['TIDService'] = field(default=None, repr=False, init=False)
    _initialized: bool = field(default=False, repr=False, init=False)
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __post_init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.transaction_id_list: List[dict] = []
        self.has_load = False
        self.browser_ready = asyncio.Event()
        self._browser_task: Optional[asyncio.Task] = None
        self._stop_flag = False
        self._current_proxy: Optional[str] = None
        self._running = False
        self._lock = asyncio.Lock()
    
    @property
    def is_running(self) -> bool:
        return self._running and self._browser_task is not None and not self._browser_task.done()
    
    def get_path_from_url(self, url_string: str) -> str:
        """Extract path and query from URL"""
        parsed = urlparse(url_string)
        path = parsed.path
        if parsed.query:
            path += "?" + parsed.query
        return path
    
    def get_last_path_segment(self, url_string: str) -> str:
        """Get the last segment of URL path"""
        parsed = urlparse(url_string)
        pathname = parsed.path
        segments = [s for s in pathname.split('/') if s]
        return segments[-1] if segments else ''
    
    def get_random_transaction_by_url(self, url: str) -> Optional[dict]:
        """
        Get a random transaction matching the URL.
        Prioritizes by matching URL and recent time.
        """
        # Filter transactions matching the URL's last path segment
        matched_transactions = sorted(
            [item for item in self.transaction_id_list 
             if self.get_last_path_segment(item['url']) == self.get_last_path_segment(url)],
            key=lambda x: x['time'],
            reverse=True
        )
        
        logger.debug(f"matchedTransactions: {matched_transactions[:3] if matched_transactions else []}")
        
        # If we have 1-2 matches, randomly select from them
        if 0 < len(matched_transactions) < 3:
            return random.choice(matched_transactions)
        
        # If we have 3+ matches, select from top 3 most recent
        if len(matched_transactions) >= 3:
            top_three = matched_transactions[:3]
            return random.choice(top_three)
        
        # No URL match - fall back to most recent 3 from entire list
        if self.transaction_id_list:
            top_transactions = sorted(
                self.transaction_id_list,
                key=lambda x: x['time'],
                reverse=True
            )[:3]
            return random.choice(top_transactions)
        
        return None
    
    def get_tid(self, path: str) -> Optional[str]:
        """
        获取 TID (同步版本，供外部调用)
        
        Args:
            path: API 路径，如 "/1.1/onboarding/task.json"
            
        Returns:
            transactionId 或 None
        """
        transaction = self.get_random_transaction_by_url(path)
        if transaction:
            return transaction.get('transactionId')
        return None
    
    def get_status(self) -> dict:
        """获取服务状态"""
        return {
            "running": self._running,
            "browser_ready": self.browser_ready.is_set(),
            "transaction_count": len(self.transaction_id_list),
            "proxy": self._current_proxy
        }
    
    async def start(self, proxy: Optional[str] = None):
        """
        启动 TID 服务
        
        Args:
            proxy: 代理地址，格式如 "socks5://user:pass@host:port"
        """
        async with self._lock:
            if self._running:
                # 如果代理相同，不需要重启
                if proxy == self._current_proxy:
                    logger.info("TID 服务已在运行中，代理相同，无需重启")
                    return
                # 代理不同，需要重启
                logger.info(f"TID 服务代理变更: {self._current_proxy} -> {proxy}，正在重启...")
                await self._stop_internal()
            
            self._current_proxy = proxy
            self._stop_flag = False
            self._running = True
            self.has_load = False
            self.browser_ready.clear()
            
            logger.info(f"正在启动 TID 服务... 代理: {proxy or '无'}")
            self._browser_task = asyncio.create_task(self._run_browser_wrapper())
    
    async def stop(self):
        """停止 TID 服务"""
        async with self._lock:
            await self._stop_internal()
    
    async def _stop_internal(self):
        """内部停止方法（不加锁）"""
        if not self._running:
            return
        
        logger.info("正在停止 TID 服务...")
        self._stop_flag = True
        self._running = False
        
        if self._browser_task:
            self._browser_task.cancel()
            try:
                await self._browser_task
            except asyncio.CancelledError:
                pass
            self._browser_task = None
        
        self.browser_ready.clear()
        logger.info("TID 服务已停止")
    
    async def wait_ready(self, timeout: float = 60.0) -> bool:
        """
        等待浏览器就绪
        
        Args:
            timeout: 超时时间(秒)
            
        Returns:
            是否就绪
        """
        try:
            await asyncio.wait_for(self.browser_ready.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"等待 TID 服务就绪超时 ({timeout}秒)")
            return False
    
    async def _handle_request(self, request):
        """Handle intercepted requests to capture x-client-transaction-id"""
        try:
            headers = request.headers
            x_client_transaction_id = headers.get('x-client-transaction-id')
            
            if x_client_transaction_id:
                obj = {
                    'transactionId': x_client_transaction_id,
                    'url': self.get_path_from_url(request.url),
                    'time': int(time.time() * 1000)
                }
                logger.debug(f"Captured TID: {obj}")
                self.transaction_id_list.append(obj)
                
                # 限制列表大小，防止内存溢出
                if len(self.transaction_id_list) > 1000:
                    self.transaction_id_list = self.transaction_id_list[-500:]
                
                if not self.has_load:
                    self.has_load = True
                    self.browser_ready.set()
                    logger.info("TID 服务就绪 - 首个 TID 已捕获!")
        except Exception as e:
            logger.error(f"处理请求时出错: {e}")
    
    async def _run_browser_wrapper(self):
        """Wrapper to catch and log browser errors"""
        try:
            await self._run_browser()
        except asyncio.CancelledError:
            logger.info("TID 浏览器任务已取消")
        except Exception as e:
            logger.error(f"TID 浏览器任务错误: {e}", exc_info=True)
            self._running = False
    
    async def _run_browser(self):
        """Run the headless browser and intercept requests"""
        from patchright.async_api import async_playwright
        
        logger.info("正在初始化 patchright 浏览器...")
        
        async with async_playwright() as p:
            logger.info("正在启动 Chrome 浏览器...")
            
            # 构建启动参数
            launch_args = [
                '--disable-blink-features=AutomationControlled',
            ]
            
            # 如果有代理，添加代理参数
            if self._current_proxy:
                # 将代理从 socks5://user:pass@host:port 格式转换
                proxy_config = self._parse_proxy_for_browser(self._current_proxy)
                logger.info(f"浏览器使用代理: {proxy_config.get('server', 'N/A')}")
                browser = await p.chromium.launch(
                    channel="chrome",
                    headless=TID_CONFIG["HEADLESS"],
                    args=launch_args,
                    proxy=proxy_config
                )
            else:
                browser = await p.chromium.launch(
                    channel="chrome",
                    headless=TID_CONFIG["HEADLESS"],
                    args=launch_args
                )
            
            logger.info("浏览器启动成功")
            
            try:
                # Create context with mobile user agent
                context = await browser.new_context(
                    user_agent=TID_CONFIG["USER_AGENT"],
                    viewport={'width': 375, 'height': 812},
                    device_scale_factor=3,
                    is_mobile=True,
                    has_touch=True,
                )
                logger.info("浏览器上下文已创建")
                
                # Create page
                page = await context.new_page()
                logger.info("新页面已创建")
                
                # Listen to all requests
                page.on("request", lambda request: asyncio.create_task(self._handle_request(request)))
                
                logger.info(f"开始加载 {TID_CONFIG['TWITTER_URL']}...")
                
                while not self._stop_flag:
                    try:
                        # 清理所有浏览器数据：cookies、localStorage、sessionStorage、缓存等
                        await context.clear_cookies()
                        
                        # 清理 localStorage 和 sessionStorage
                        try:
                            await page.evaluate("""() => {
                                try { localStorage.clear(); } catch(e) {}
                                try { sessionStorage.clear(); } catch(e) {}
                            }""")
                        except Exception:
                            pass  # 页面可能还没加载，忽略错误
                        
                        logger.debug("已清除 cookies/storage，正在导航到页面...")
                        
                        # Navigate to Twitter
                        await page.goto(TID_CONFIG["TWITTER_URL"], wait_until="domcontentloaded", timeout=30000)
                        logger.debug("页面加载完成 (domcontentloaded)")
                        
                        # Wait a bit for page to stabilize
                        await asyncio.sleep(1)
                        
                        # Try to click login button (like in original code)
                        try:
                            login_link = page.locator('a[href="/login"]')
                            if await login_link.count() > 0:
                                await login_link.click()
                                logger.debug("已点击登录按钮")
                        except Exception as e:
                            logger.debug(f"点击登录失败（可能正常）: {e}")
                        
                        logger.info(f"页面已加载。TID 总数: {len(self.transaction_id_list)}. 等待 {TID_CONFIG['REFRESH_INTERVAL']}秒后刷新...")
                        
                        # 分段等待，以便能够响应停止信号
                        for _ in range(TID_CONFIG['REFRESH_INTERVAL']):
                            if self._stop_flag:
                                break
                            await asyncio.sleep(1)
                        
                    except Exception as e:
                        logger.error(f"浏览器导航错误: {e}")
                        await asyncio.sleep(5)
            finally:
                await browser.close()
                logger.info("浏览器已关闭")
    
    def _parse_proxy_for_browser(self, proxy_str: str) -> dict:
        """
        将代理字符串转换为 Playwright 代理配置格式
        
        支持格式:
        - socks5://user:pass@host:port
        - socks5://host:port
        - http://user:pass@host:port
        - http://host:port
        """
        if not proxy_str:
            return {}
        
        proxy_config = {"server": proxy_str}
        
        # 解析用户名和密码
        if '@' in proxy_str:
            # 格式: protocol://user:pass@host:port
            import re
            match = re.match(r'(\w+)://([^:]+):([^@]+)@(.+)', proxy_str)
            if match:
                protocol, username, password, server = match.groups()
                proxy_config = {
                    "server": f"{protocol}://{server}",
                    "username": username,
                    "password": password
                }
        
        return proxy_config


# 创建全局 TID 服务实例
# 使用函数延迟初始化，避免在导入时就初始化
_tid_service_instance: Optional[TIDService] = None


def get_tid_service() -> TIDService:
    """获取 TID 服务单例"""
    global _tid_service_instance
    if _tid_service_instance is None:
        _tid_service_instance = TIDService()
        _tid_service_instance.__post_init__()
    return _tid_service_instance

