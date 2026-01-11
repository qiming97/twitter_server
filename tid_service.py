"""
TID 服务 - 集成的 Twitter Transaction ID 获取服务
使用 patchright 浏览器捕获 Twitter 请求中的 x-client-transaction-id

注意：为了兼容 Windows，浏览器在单独的线程中运行（使用同步 API）
"""
import asyncio
import time
import logging
import random
import threading
from urllib.parse import urlparse
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor

# Setup logging
logger = logging.getLogger(__name__)

# TID 服务配置
TID_CONFIG = {
    "TWITTER_URL": "https://x.com/elonmusk",
    "USER_AGENT": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1 Edg/141.0.0.0",
    "REFRESH_INTERVAL": 10,  # 页面刷新间隔(秒)
    "HEADLESS": True,
}


class TIDService:
    """TID 服务单例类 - 使用线程运行浏览器以兼容 Windows"""
    _instance: Optional['TIDService'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self.transaction_id_list: List[dict] = []
        self.has_load = False
        self._browser_ready_event = threading.Event()
        self._stop_flag = False
        self._current_proxy: Optional[str] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tid_browser")
    
    @property
    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()
    
    @property
    def browser_ready(self) -> bool:
        """兼容旧接口"""
        return self._browser_ready_event.is_set()
    
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
            "browser_ready": self._browser_ready_event.is_set(),
            "transaction_count": len(self.transaction_id_list),
            "proxy": self._current_proxy
        }
    
    async def start(self, proxy: Optional[str] = None):
        """
        启动 TID 服务
        
        Args:
            proxy: 代理地址，格式如 "socks5://user:pass@host:port"
        """
        if self._running:
            # 如果代理相同，不需要重启
            if proxy == self._current_proxy:
                logger.info("TID 服务已在运行中，代理相同，无需重启")
                return
            # 代理不同，需要重启
            logger.info(f"TID 服务代理变更: {self._current_proxy} -> {proxy}，正在重启...")
            await self.stop()
        
        self._current_proxy = proxy
        self._stop_flag = False
        self._running = True
        self.has_load = False
        self._browser_ready_event.clear()
        
        logger.info(f"正在启动 TID 服务... 代理: {proxy or '无'}")
        
        # 在单独的线程中运行浏览器
        self._thread = threading.Thread(
            target=self._run_browser_sync,
            name="tid_browser_thread",
            daemon=True
        )
        self._thread.start()
    
    async def stop(self):
        """停止 TID 服务"""
        if not self._running:
            return
        
        logger.info("正在停止 TID 服务...")
        self._stop_flag = True
        self._running = False
        
        # 等待线程结束
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
            if self._thread.is_alive():
                logger.warning("TID 浏览器线程未能在超时时间内停止")
        
        self._thread = None
        self._browser_ready_event.clear()
        logger.info("TID 服务已停止")
    
    async def wait_ready(self, timeout: float = 60.0) -> bool:
        """
        等待浏览器就绪
        
        Args:
            timeout: 超时时间(秒)
            
        Returns:
            是否就绪
        """
        # 在线程中等待
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._browser_ready_event.wait(timeout=timeout)
        )
        if not result:
            logger.warning(f"等待 TID 服务就绪超时 ({timeout}秒)")
        return result
    
    def _handle_request_sync(self, request):
        """Handle intercepted requests to capture x-client-transaction-id (同步版本)"""
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
                    self._browser_ready_event.set()
                    logger.info("TID 服务就绪 - 首个 TID 已捕获!")
        except Exception as e:
            logger.error(f"处理请求时出错: {e}")
    
    def _run_browser_sync(self):
        """在单独线程中运行浏览器（同步版本，兼容 Windows）"""
        try:
            from patchright.sync_api import sync_playwright
            
            logger.info("正在初始化 patchright 浏览器 (同步模式)...")
            
            with sync_playwright() as p:
                logger.info("正在启动 Chrome 浏览器...")
                
                # 构建启动参数
                launch_args = [
                    '--disable-blink-features=AutomationControlled',
                ]
                
                # 如果有代理，通过命令行参数配置（支持 SOCKS5）
                proxy_config = None
                if self._current_proxy:
                    proxy_info = self._parse_proxy_for_browser(self._current_proxy)
                    proxy_server = proxy_info.get('server', '')
                    
                    # 检查是否是 SOCKS5 代理
                    if 'socks5' in proxy_server.lower():
                        # SOCKS5 代理通过命令行参数配置
                        # 格式: --proxy-server=socks5://host:port
                        launch_args.append(f'--proxy-server={proxy_server}')
                        logger.info(f"浏览器使用 SOCKS5 代理 (命令行): {proxy_server}")
                    else:
                        # HTTP/HTTPS 代理可以使用 Playwright 原生支持
                        proxy_config = proxy_info
                        logger.info(f"浏览器使用代理: {proxy_server}")
                
                if proxy_config:
                    browser = p.chromium.launch(
                        channel="chrome",
                        headless=TID_CONFIG["HEADLESS"],
                        args=launch_args,
                        proxy=proxy_config
                    )
                else:
                    browser = p.chromium.launch(
                        channel="chrome",
                        headless=TID_CONFIG["HEADLESS"],
                        args=launch_args
                    )
                
                logger.info("浏览器启动成功")
                
                try:
                    # Create context with mobile user agent
                    context = browser.new_context(
                        user_agent=TID_CONFIG["USER_AGENT"],
                        viewport={'width': 375, 'height': 812},
                        device_scale_factor=3,
                        is_mobile=True,
                        has_touch=True,
                    )
                    logger.info("浏览器上下文已创建")
                    
                    # Create page
                    page = context.new_page()
                    logger.info("新页面已创建")
                    
                    # Listen to all requests (同步回调)
                    page.on("request", self._handle_request_sync)
                    
                    logger.info(f"开始加载 {TID_CONFIG['TWITTER_URL']}...")
                    
                    while not self._stop_flag:
                        try:
                            # 清理所有浏览器数据
                            context.clear_cookies()
                            
                            # 清理 localStorage 和 sessionStorage
                            try:
                                page.evaluate("""() => {
                                    try { localStorage.clear(); } catch(e) {}
                                    try { sessionStorage.clear(); } catch(e) {}
                                }""")
                            except Exception:
                                pass  # 页面可能还没加载，忽略错误
                            
                            logger.debug("已清除 cookies/storage，正在导航到页面...")
                            
                            # Navigate to Twitter
                            page.goto(TID_CONFIG["TWITTER_URL"], wait_until="domcontentloaded", timeout=30000)
                            logger.debug("页面加载完成 (domcontentloaded)")
                            
                            # Wait a bit for page to stabilize
                            time.sleep(1)
                            
                            # Try to click login button
                            try:
                                login_link = page.locator('a[href="/login"]')
                                if login_link.count() > 0:
                                    login_link.click()
                                    logger.debug("已点击登录按钮")
                            except Exception as e:
                                logger.debug(f"点击登录失败（可能正常）: {e}")
                            
                            logger.info(f"页面已加载。TID 总数: {len(self.transaction_id_list)}. 等待 {TID_CONFIG['REFRESH_INTERVAL']}秒后刷新...")
                            
                            # 分段等待，以便能够响应停止信号
                            for _ in range(TID_CONFIG['REFRESH_INTERVAL']):
                                if self._stop_flag:
                                    break
                                time.sleep(1)
                            
                        except Exception as e:
                            logger.error(f"浏览器导航错误: {e}")
                            time.sleep(5)
                finally:
                    browser.close()
                    logger.info("浏览器已关闭")
                    
        except Exception as e:
            logger.error(f"TID 浏览器线程错误: {e}", exc_info=True)
        finally:
            self._running = False
    
    def _parse_proxy_for_browser(self, proxy_str: str) -> dict:
        """
        将代理字符串转换为 Playwright 代理配置格式
        
        支持格式:
        - socks5://user:pass@host:port
        - socks5://host:port
        - http://user:pass@host:port
        - http://host:port
        
        注意：SOCKS5 代理通过命令行参数配置，认证信息会包含在 URL 中
        """
        if not proxy_str:
            return {}
        
        import re
        
        # 解析用户名和密码
        if '@' in proxy_str:
            # 格式: protocol://user:pass@host:port
            match = re.match(r'(\w+)://([^:]+):([^@]+)@(.+)', proxy_str)
            if match:
                protocol, username, password, server = match.groups()
                
                # 对于 SOCKS5，保持完整 URL（Chrome 命令行支持 socks5://user:pass@host:port）
                if 'socks' in protocol.lower():
                    return {
                        "server": proxy_str,  # 保持完整 URL 包含认证信息
                        "username": username,
                        "password": password
                    }
                else:
                    # HTTP/HTTPS 代理
                    return {
                        "server": f"{protocol}://{server}",
                        "username": username,
                        "password": password
                    }
        
        return {"server": proxy_str}


# 创建全局 TID 服务实例
_tid_service_instance: Optional[TIDService] = None


def get_tid_service() -> TIDService:
    """获取 TID 服务单例"""
    global _tid_service_instance
    if _tid_service_instance is None:
        _tid_service_instance = TIDService()
    return _tid_service_instance
