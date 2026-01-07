"""
Twitter API 核心请求客户端
"""
import asyncio
import json
import random
import re
import time
import warnings
from typing import Optional, Dict, Any

from curl_cffi import requests as cffi_requests
import urllib3

# 禁用 SSL 证书验证警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

from config import settings
from exceptions import (
    TwitterError, 
    AccountSuspendedError, 
    AccountNotFoundError,
    CloudflareError,
    PasswordResetRequiredError,
    EmailMismatchError
)
import utils


class TwitterClient:
    """Twitter API 客户端"""
    
    def __init__(
        self, 
        cookie: str = "",
        useragent: str = "",
        proxy: Optional[str] = None,
        password: str = ""
    ):  
        # 清理 cookie 格式
        cookie = cookie.replace(" ", "")
        # 修正 ct0=ct0:xxx 为 ct0=xxx
        cookie = re.sub(r'ct0=ct0:', 'ct0=', cookie)
        self.cookie = cookie
        self.useragent = useragent or self._default_useragent()
        self.proxy = utils.parse_proxy(proxy) if proxy else None
        self.password = password
        
        # 从cookie解析关键信息
        self.csrf_token = utils.extract_ct0(cookie)
        self.twid = utils.extract_twid(cookie)
        self.tw_user_id = utils.extract_user_id_from_twid(self.twid)
        
        # 初始化session
        self.session: Optional[cffi_requests.Session] = None
        self.session_headers: Dict[str, str] = {}
        
        # 账号信息
        self.username = ""
        self.follower_count = 0
        self.following_count = 0
        self.country = ""
        self.create_time = ""
        self.is_premium = False
        self.verify = False  # 密码验证状态
        
        self._init_session()
    
    @property
    def graphql_headers(self) -> Dict[str, str]:
        """GraphQL API 通用请求头 (不包含csrf token，因为已在session_headers中)"""
        return {
            "x-twitter-active-user": "yes",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "x-twitter-auth-type": "OAuth2Session",
            "authorization": settings.TWITTER_BEARER_TOKEN,
            "user-agent": self.useragent,
        }
    
    def _default_useragent(self) -> str:
        return "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    def _init_session(self):
        """初始化请求session"""
        proxies_dict = None
        if self.proxy:
            proxies_dict = {
                "http": self.proxy,
                "https": self.proxy
            }
        
        # 使用 curl_cffi 模拟 Chrome 浏览器
        self.session = cffi_requests.Session(
            impersonate="chrome120", 
            proxies=proxies_dict, 
            verify=False
        )
        
        self.session_headers = {
            "x-twitter-active-user": "yes",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "x-csrf-token": self.csrf_token,
            "x-twitter-auth-type": "OAuth2Session",
            "authorization": settings.TWITTER_BEARER_TOKEN,
            "user-agent": self.useragent,
            "cookie": self.cookie,
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "accept-encoding": "gzip, deflate, br",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "dnt": "1",
            "connection": "keep-alive",
            "upgrade-insecure-requests": "1",
        }
        self.session.headers.update(self.session_headers)
    
    def _sync_session_headers(self):
        """同步 session_headers 到 session.headers"""
        self.session_headers['x-csrf-token'] = self.csrf_token
        self.session_headers['cookie'] = self.cookie
        self.session.headers.update(self.session_headers)
    
    # ==================== 通用网络重试工具 ====================
    
    @staticmethod
    def is_network_error(error_msg: str) -> bool:
        """
        判断是否为网络错误 (静态方法，可外部调用)
        """
        network_keywords = [
            'ssl', 'timeout', 'connection', 'network', 'socket', 
            'max retries', 'refused', 'reset', 'eof', 'connect', 
            'tunnel', 'curl', 'failed to perform', '502', '503', '504',
            'timed out', 'unreachable', 'dns', 'proxy', 'handshake'
        ]
        error_lower = error_msg.lower()
        return any(keyword in error_lower for keyword in network_keywords)
    
    def retry_sync(
        self, 
        func, 
        *args, 
        max_retries: int = 3, 
        retry_delay: float = 2.0,
        on_retry: callable = None,
        **kwargs
    ):
        """
        通用同步重试函数
        
        Args:
            func: 要执行的函数
            *args: 函数参数
            max_retries: 最大重试次数
            retry_delay: 基础重试延迟(秒)，实际延迟会递增
            on_retry: 重试时的回调函数 on_retry(attempt, error, wait_time)
            **kwargs: 函数关键字参数
            
        Returns:
            函数返回值
            
        Example:
            result = client.retry_sync(
                session.get, 
                "https://api.example.com",
                max_retries=3,
                timeout=30
            )
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                error_str = str(e)
                
                # 非网络错误，直接抛出
                if not self.is_network_error(error_str):
                    raise
                
                # 最后一次尝试，抛出错误
                if attempt >= max_retries - 1:
                    raise
                
                # 计算等待时间 (递增 + 随机抖动)
                wait_time = retry_delay * (attempt + 1) + random.uniform(0.5, 1.5)
                
                # 回调或默认日志
                if on_retry:
                    on_retry(attempt + 1, error_str, wait_time)
                else:
                    print(f"网络错误，{wait_time:.1f}秒后重试 ({attempt + 1}/{max_retries}): {error_str[:50]}")
                
                time.sleep(wait_time)
        
        raise last_error
    
    async def retry_async(
        self, 
        func, 
        *args, 
        max_retries: int = 3, 
        retry_delay: float = 2.0,
        on_retry: callable = None,
        **kwargs
    ):
        """
        通用异步重试函数
        
        Args:
            func: 要执行的异步函数
            *args: 函数参数
            max_retries: 最大重试次数
            retry_delay: 基础重试延迟(秒)
            on_retry: 重试时的回调函数 on_retry(attempt, error, wait_time)
            **kwargs: 函数关键字参数
            
        Returns:
            函数返回值
            
        Example:
            result = await client.retry_async(
                client.get_user_info,
                "username",
                max_retries=3
            )
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # 判断是否为协程函数
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                error_str = str(e)
                
                # 非网络错误，直接抛出
                if not self.is_network_error(error_str):
                    raise
                
                # 最后一次尝试，抛出错误
                if attempt >= max_retries - 1:
                    raise
                
                # 计算等待时间
                wait_time = retry_delay * (attempt + 1) + random.uniform(0.5, 1.5)
                
                # 回调或默认日志
                if on_retry:
                    on_retry(attempt + 1, error_str, wait_time)
                else:
                    print(f"网络错误，{wait_time:.1f}秒后重试 ({attempt + 1}/{max_retries}): {error_str[:50]}")
                
                await asyncio.sleep(wait_time)
        
        raise last_error
    
    # ==================== 便捷请求方法 ====================
    
    def _session_request(self, method: str, url: str, max_retries: int = 2, **kwargs):
        """
        使用 self.session 发送请求 (带重试机制)
        """
        def do_request():
            self._sync_session_headers()
            if method.upper() == "GET":
                return self.session.get(url, timeout=30, **kwargs)
            else:
                return self.session.post(url, timeout=30, **kwargs)
        
        return self.retry_sync(do_request, max_retries=max_retries)
    
    async def _send(self, url: str, max_retries: int = 3, **kwargs) -> Any:
        """
        发送HTTP请求 (带网络重试机制)
        
        Args:
            url: 请求URL
            max_retries: 最大重试次数，默认3次
            **kwargs: 其他请求参数
        """
        method = kwargs.pop('method', 'GET')
        last_error = None
        
        for attempt in range(max_retries):
            # 添加随机延迟
            delay = random.uniform(0.8, 2.0) if method == 'POST' else random.uniform(0.3, 1.0)
            await asyncio.sleep(delay)
            
            try:
                # 确保使用最新的 csrf_token 和 cookie
                self._sync_session_headers()
                
                request_headers = dict(self.session_headers)
                if 'headers' in kwargs:
                    request_headers.update(kwargs['headers'])
                kwargs['headers'] = request_headers

                
                response = self.session.request(method, url, timeout=30, **kwargs)
                
                # 自动更新cookie
                if response.cookies:
                    await self._update_cookies_from_response(response)
                
                # 检测Cloudflare拦截
                if response.status_code == 401:
                    if "cloudflare" in response.text.lower() or "blocked" in response.text.lower():
                        raise CloudflareError("Cloudflare验证失败(401)")
                elif response.status_code in [403, 503]:
                    if "cloudflare" in response.text.lower():
                        raise CloudflareError("Cloudflare验证")
                
                # 服务端错误，可重试
                if response.status_code in [502, 503, 504]:
                    raise TwitterError(f"服务器错误({response.status_code})")
                
                return response
                
            except CloudflareError:
                raise  # Cloudflare错误不重试
            except TwitterError as e:
                last_error = e
                error_str = str(e)
                # 判断是否网络错误，可重试
                if self._is_network_error(error_str):
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2 + random.uniform(0.5, 1.5)
                        print(f"网络错误，{wait_time:.1f}秒后重试 ({attempt + 1}/{max_retries}): {error_str[:50]}")
                        await asyncio.sleep(wait_time)
                        continue
                raise
            except Exception as e:
                last_error = e
                error_str = str(e)
                # 网络相关错误，重试
                if self._is_network_error(error_str):
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2 + random.uniform(0.5, 1.5)
                        print(f"网络错误，{wait_time:.1f}秒后重试 ({attempt + 1}/{max_retries}): {error_str[:50]}")
                        await asyncio.sleep(wait_time)
                        continue
                raise TwitterError(f"网络请求失败: {error_str}")
        
        raise TwitterError(f"重试{max_retries}次后仍失败: {last_error}")
    
    async def _update_cookies_from_response(self, response):
        """从响应更新cookie"""
        try:
            response_cookies = {}
            if hasattr(response, 'cookies'):
                if hasattr(response.cookies, 'get_dict'):
                    response_cookies = response.cookies.get_dict()
                elif isinstance(response.cookies, dict):
                    response_cookies = response.cookies
                else:
                    try:
                        response_cookies = dict(response.cookies)
                    except:
                        pass
            
            if response_cookies:
                current_cookie = self.session_headers.get('cookie', '')
                cookie_dict = utils.parse_cookie_string(current_cookie)
                cookie_dict.update(response_cookies)
                
                new_cookie = utils.cookies_to_string(cookie_dict)
                self.session_headers['cookie'] = new_cookie
                self.session.headers['cookie'] = new_cookie
                self.cookie = new_cookie
                
                # 更新csrf_token
                if 'ct0' in response_cookies:
                    self.csrf_token = response_cookies['ct0']
                    # 使用小写保持一致
                    self.session_headers['x-csrf-token'] = self.csrf_token
                    self.session.headers['x-csrf-token'] = self.csrf_token
                    print(f"✓ csrf_token 已更新: {self.csrf_token[:20]}...")
                
                return True
        except:
            pass
        return False
    
    async def check_account_suspended(self, username: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        检查账号是否被冻结 (带网络重试机制)
        使用独立的 session，先请求用户主页获取 cookie，再调用 GraphQL API
        
        返回:
        {
            "suspended": bool,  # 是否冻结
            "exists": bool,     # 账号是否存在
            "message": str      # 详细信息
        }
        """
        last_error = None
        
        for attempt in range(max_retries):
            result = await self._do_check_account_suspended(username)
            
            # 如果不是网络错误，直接返回
            if not result.get("error") or result.get("exists") is not None:
                return result
            
            # 网络错误，重试
            last_error = result.get("message", "未知错误")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2 + random.uniform(0.5, 1.5)
                print(f"检查冻结状态网络错误，{wait_time:.1f}秒后重试 ({attempt + 1}/{max_retries}): {last_error[:50]}")
                await asyncio.sleep(wait_time)
        
        return {
            "suspended": False,
            "exists": None,
            "error": True,
            "message": f"重试{max_retries}次后仍失败: {last_error}"
        }
    
    async def _do_check_account_suspended(self, username: str) -> Dict[str, Any]:
        """执行检查账号冻结状态的核心逻辑"""
        check_session = None
        
        try:
            # 1. 创建独立 session
            proxies_dict = None
            if self.proxy:
                proxies_dict = {
                    "http": self.proxy,
                    "https": self.proxy
                }
            
            check_session = cffi_requests.Session(
                impersonate="chrome120",
                proxies=proxies_dict,
                verify=False
            )
            
            # 2. 先请求用户主页获取 cookie (带重试)
            page_url = f"https://x.com/{username}"
            page_headers = {
                "User-Agent": self.useragent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            
            page_response = self._request_with_retry(
                check_session, "GET", page_url, 
                headers=page_headers, timeout=30
            )
            
            # 从响应中提取 cookie
            ct0 = check_session.cookies.get("ct0", "").strip()
            if ct0 and ct0.startswith("ct0:"):
                ct0 = ct0[4:].strip()
            
            # 3. 获取 tid 和构建请求
            url = "https://api.x.com/graphql/-oaLodhGbbnzJBACb1kk2Q/UserByScreenName"
            tid = utils.get_tid("/graphql/-oaLodhGbbnzJBACb1kk2Q/UserByScreenName")
            
            request_headers = {
                "x-twitter-active-user": "yes",
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "Authorization": settings.TWITTER_BEARER_TOKEN,
                "User-Agent": self.useragent,
                "accept": "*/*",
                "accept-language": "en-US,en;q=0.9",
                "Referer": f"https://x.com/{username}",
                "X-Client-Transaction-Id": tid,
            }
            
            if ct0:
                request_headers["x-csrf-token"] = ct0

            params = {
                "variables": json.dumps({
                    "screen_name": username,
                    "withSafetyModeUserFields": True
                }),
                "features": json.dumps({
                    "hidden_profile_likes_enabled": True,
                    "hidden_profile_subscriptions_enabled": True,
                    "responsive_web_graphql_exclude_directive_enabled": True,
                    "verified_phone_label_enabled": False,
                    "responsive_web_profile_redirect_enabled": False,
                    "subscriptions_verification_info_is_identity_verified_enabled": True,
                    "subscriptions_verification_info_verified_since_enabled": True,
                    "subscriptions_feature_can_gift_premium": True,
                    "rweb_tipjar_consumption_enabled": True,
                    "profile_label_improvements_pcf_label_in_post_enabled": True,
                    "highlights_tweets_tab_ui_enabled": True,
                    "responsive_web_twitter_article_notes_tab_enabled": True,
                    "creator_subscriptions_tweet_preview_api_enabled": True,
                    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                    "responsive_web_graphql_timeline_navigation_enabled": True
                }),
                "fieldToggles": json.dumps({
                    "withAuxiliaryUserLabels": False
                }),
            }
            
            # 4. 发送 GraphQL 请求 (带重试)
            await asyncio.sleep(random.uniform(0.3, 1.0))
            response = self._request_with_retry(
                check_session, "GET", url,
                headers=request_headers, params=params, timeout=30
            )
            
            if response.status_code == 404:
                return {
                    "suspended": False,
                    "exists": False,
                    "message": "账号不存在"
                }
            
            resp_json = response.json()
            data = resp_json.get('data', {})
            
            # 情况1: data 为空且 user 不存在 → 唯一可靠的账号不存在判断
            # 注意: 只有明确返回空 data 或 user 为 null 时才判断不存在
            user_data = data.get('user') if data else None
            if data is not None and 'user' in data and user_data is None:
                # API 明确返回了 user: null，账号确实不存在
                return {
                    "suspended": False,
                    "exists": False,
                    "message": "账号不存在"
                }
            
            # 如果 data 为空或没有 user 字段，可能是网络/解析问题，返回未知
            if not data or 'user' not in data:
                return {
                    "suspended": False,
                    "exists": None,
                    "error": True,
                    "message": "API返回数据异常，无法判断账号状态"
                }
            
            result = data.get('user', {}).get('result', {})
            typename = result.get('__typename', '')
            
            # 情况2: UserUnavailable → 检查是否冻结
            if typename == 'UserUnavailable':
                reason = result.get('reason', '')
                message = result.get('message', '')
                if reason == 'Suspended' or 'suspended' in message.lower():
                    return {
                        "suspended": True,
                        "exists": True,
                        "message": "账号已被冻结"
                    }
                else:
                    # 不可用但非冻结，可能是其他原因（如被限制），不能确定是否存在
                    return {
                        "suspended": False,
                        "exists": None,
                        "error": True,
                        "message": f"账号不可用: {reason or message}"
                    }
            
            # 情况3: User → 账号正常
            if typename == 'User':
                return {
                    "suspended": False,
                    "exists": True,
                    "message": "账号正常"
                }
            
            # 未知状态，返回 exists: None 表示无法判断
            return {
                "suspended": False,
                "exists": None,
                "error": True,
                "message": f"未知状态: {typename}"
            }
            
        except Exception as e:
            error_msg = str(e)
            is_network_error = self._is_network_error(error_msg)
            
            if is_network_error:
                return {
                    "suspended": False,
                    "exists": None,  # None 表示未知，需要重试
                    "error": True,
                    "message": f"网络错误: {error_msg[:100]}"
                }
            else:
                return {
                    "suspended": False,
                    "exists": False,
                    "error": True,
                    "message": f"检查失败: {error_msg[:100]}"
                }
        finally:
            if check_session:
                try:
                    check_session.close()
                except:
                    pass
    
    async def get_user_info(self, username: str) -> Dict[str, Any]:
        """获取用户详细信息"""
        url = "https://api.x.com/graphql/-oaLodhGbbnzJBACb1kk2Q/UserByScreenName"
        tid = utils.get_tid("/graphql/-oaLodhGbbnzJBACb1kk2Q/UserByScreenName")
        
        
        # 合并 graphql_headers，并添加特定请求头
        headers = dict(self.graphql_headers)
        headers.update({
            "referer": f"https://x.com/{username}",
            "x-csrf-token": self.csrf_token,  # 确保使用最新的csrf_token
            "x-client-transaction-id": tid,
        })
        
        params = {
                "variables": json.dumps({
                    "screen_name": username,
                    "withSafetyModeUserFields": True
                }),
                "features": json.dumps({
                    "hidden_profile_likes_enabled": True,
                    "hidden_profile_subscriptions_enabled": True,
                    "responsive_web_graphql_exclude_directive_enabled": True,
                    "verified_phone_label_enabled": False,
                    "responsive_web_profile_redirect_enabled":False,
                    "subscriptions_verification_info_is_identity_verified_enabled": True,
                    "subscriptions_verification_info_verified_since_enabled": True,
                    "subscriptions_feature_can_gift_premium":True,
                    "rweb_tipjar_consumption_enabled":True,
                    "profile_label_improvements_pcf_label_in_post_enabled":True,
                    "highlights_tweets_tab_ui_enabled": True,
                    "responsive_web_twitter_article_notes_tab_enabled": True,
                    "creator_subscriptions_tweet_preview_api_enabled": True,
                    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                    "responsive_web_graphql_timeline_navigation_enabled": True
                }),
                "fieldToggles": json.dumps({
                    "withAuxiliaryUserLabels": False
                }),
            }
        
        response = await self._send(url, headers=headers, params=params, method="GET")
   
        if response.status_code > 210:
            raise TwitterError(f"获取用户信息失败: {response.text}")
        
        return response.json()
    
    async def get_premium_info(self) -> Dict[str, Any]:
        """获取会员信息"""
        tid = utils.get_tid("/i/api/graphql/qkST2QW7-FounZecuam93g/PremiumHubQuery")
        
        url = "https://x.com/i/api/graphql/qkST2QW7-FounZecuam93g/PremiumHubQuery?variables=%7B%7D"
        headers = {
            "referer": "https://x.com/i/premium",
            "x-client-transaction-id": tid,
            "x-csrf-token": self.csrf_token,  # 确保包含最新的csrf_token
        }
        
        response = await self._send(url, headers=headers, method="GET")
        return response.json()
    
    async def verify_password(self, password: str) -> Dict[str, Any]:
        """验证密码并获取账号数据 (带网络重试)"""
        data = {'password': password}
        
        response = self._session_request(
            "POST",
            'https://x.com/i/api/1.1/account/verify_password.json',
            data=data
        )
        
        if response.status_code > 210:
            if '/i/flow/consent_flow' in response.text:
                # 需要解锁
                await self._consent_flow_task()
                return await self.verify_password(password)
            else:
                raise TwitterError(f"验证密码错误: {response.text}")
        
        if not response.text or not response.text.strip():
            raise TwitterError("API返回空响应")
        
        try:
            resp_json = response.json()
        except:
            raise TwitterError(f"JSON解析失败")
        
        if "errors" in resp_json:
            raise TwitterError(f"验证密码错误: {response.text}")
        
        if resp_json.get("status") == "ok":
            # 获取更多账号信息 (带重试)
            p13n_resp = self._session_request(
                "GET",
                'https://x.com/i/api/1.1/account/personalization/p13n_data.json'
            )
            if p13n_resp.text and p13n_resp.text.strip():
                try:
                    return p13n_resp.json()
                except:
                    pass
        
        return resp_json
    
    async def _consent_flow_task(self):
        """解锁任务"""
        tid = utils.get_tid("/1.1/onboarding/task.json")
        headers = {
            "referer": "https://x.com/",
            "x-client-transaction-id": tid
        }
        
        # Step 1
        payload = {
            "input_flow_data": {
                "flow_context": {
                    "debug_overrides": {},
                    "start_location": {"location": "manual_link"}
                }
            },
            "subtask_versions": {}
        }
        
        response = await self._send(
            "https://api.x.com/1.1/onboarding/task.json?flow_name=consent_flow",
            headers=headers,
            json=payload,
            method="POST"
        )
        
        if response.status_code != 200:
            raise TwitterError(f"consent_flow失败: {response.text}")
        
        resp = response.json()
        flow_token = resp["flow_token"]
        
        # Step 2: 同意条款
        payload = {
            "flow_token": flow_token,
            "subtask_inputs": [{
                "subtask_id": "TermsOfServiceConsentCallToAction",
                "cta": {"link": "consent_agree_link"}
            }]
        }
        
        response = await self._send(
            "https://api.x.com/1.1/onboarding/task.json",
            headers=headers,
            json=payload,
            method="POST"
        )
        
        if response.status_code != 200:
            raise TwitterError(f"consent_flow2失败: {response.text}")
    
    async def get_notifications(self) -> Dict[str, Any]:
        """获取通知（用于备用获取用户信息）"""
        response = await self._send('https://x.com/i/api/2/notifications/all.json')
        return response.json()
    
    async def get_settings_page(self) -> Optional[str]:
        """访问设置页面获取 tw_user_id (带网络重试)"""
        try:
            response = self._session_request(
                "GET",
                "https://x.com/settings",
                headers={
                    'x-csrf-token': self.csrf_token,
                    'cookie': self.cookie,
                }
            )
            twid_cookie = response.cookies.get('twid')
            if twid_cookie:
                twid_cookie = twid_cookie.replace("u%3D", '')
                self.tw_user_id = twid_cookie
                return twid_cookie
        except Exception as e:
            print(f"获取设置页面失败: {e}")
        return None
    
    async def account_data(self, password: str) -> Dict[str, Any]:
        """
        获取账号完整数据 (参照 twitter-modify/twitter.py 的 accountData 逻辑)
        
        流程:
        1. 验证密码获取账号数据
        2. 获取 tw_user_id
        3. 获取用户详细信息
        4. 获取会员信息
        """
        self.password = password
        
        # 1. 验证密码并获取账号数据
        account_resp = await self._account_data_api(password)
        
        if account_resp is not None:
            self.country = account_resp.get("sign_up_details", {}).get("country", "")
        
        # 2. 获取 tw_user_id
        if not self.tw_user_id:
            settings_resp = await utils.retry_async(self.get_settings_page, retries=3)
            if settings_resp is None:
                raise TwitterError("获取tw_userid失败")
        
        
        # 3. 获取用户详细信息
        user_info = await self.get_user_info(self.username)
        
        # 4. 获取会员信息
        premium_info = await self.get_premium_info()
        
        is_verified = False
        try:
            is_verified = (
                premium_info is not None and 
                premium_info.get('data') is not None and 
                premium_info.get('data', {}).get('premium_hub_config') is not None
            )
        except Exception:
            is_verified = False
        
        self.is_premium = is_verified
        
        # 5. 从用户信息中提取粉丝数等
        try:
            result = user_info.get('data', {}).get('user', {}).get('result', {})
            legacy = result.get('legacy', {})
            core = result.get('core', {})
            
            self.following_count = legacy.get("friends_count", 0)
            self.follower_count = legacy.get("followers_count", 0)
            # created_at 在 core 中，不在 legacy 中
            self.create_time = core.get("created_at", "") or legacy.get("created_at", "")
        except Exception as e:
            print(f"从用户信息获取粉丝失败: {e}")
        
        # 6. 备用方式：从通知API获取
        try:
            notifications_resp = await self.get_notifications()
            users = notifications_resp.get("globalObjects", {}).get("users", {})
            for user_key in users:
                if len(users) == 1:
                    user = users[user_key]
                    self.following_count = user.get("friends_count", self.following_count)
                    self.create_time = user.get("created_at", self.create_time)
                    self.follower_count = user.get("followers_count", self.follower_count)
                    break
                elif user_key in (self.twid or ""):
                    user = users[user_key]
                    self.following_count = user.get("friends_count", self.following_count)
                    self.create_time = user.get("created_at", self.create_time)
                    self.follower_count = user.get("followers_count", self.follower_count)
                    break
        except Exception:
            print("从通知API获取用户信息失败")
        
        return {
            'country': self.country,
            'following_count': self.following_count,
            'follower_count': self.follower_count,
            'create_time': self.create_time,
            'is_premium': self.is_premium
        }
    
    async def _account_data_api(self, password: str, ignore_consent: bool = False) -> Optional[Dict[str, Any]]:
        """
        验证密码并获取账号数据 (带网络重试)
        参照 twitter.py 的 accountDataApi 逻辑
        """
        # 1. 先访问 x.com/home 预热 session，获取最新 cookie (带重试)
        timestamp = int(time.time() * 1000)
        prefetch_url = f'https://x.com/home?prefetchTimestamp={timestamp}'
        
        prefetch_resp = self._session_request(
            "GET", prefetch_url,
            headers={
                'x-csrf-token': self.csrf_token,
                'cookie': self.cookie,
            }
        )
        
        # 从响应更新 cookie
        if prefetch_resp.cookies:
            try:
                resp_cookies = prefetch_resp.cookies.get_dict() if hasattr(prefetch_resp.cookies, 'get_dict') else dict(prefetch_resp.cookies)
                
                # 更新 cookie
                if resp_cookies:
                    cookie_dict = utils.parse_cookie_string(self.cookie)
                    cookie_dict.update(resp_cookies)
                    self.cookie = utils.cookies_to_string(cookie_dict)
                    
                    # 如果有新的 ct0，更新 csrf_token
                    if 'ct0' in resp_cookies:
                        self.csrf_token = resp_cookies['ct0']
            except Exception:
                pass
        
        # 2. 验证密码 (带重试)
        data = {'password': password}
        tid = utils.get_tid("/i/api/1.1/account/verify_password.json")
        
        response = self._session_request(
            "POST",
            'https://x.com/i/api/1.1/account/verify_password.json',
            data=data
        )
        
        if response.status_code > 210:
            if '/i/flow/consent_flow' in response.text:
                print("验证密码错误,需要解锁")
                await self._consent_flow_task()
                if not ignore_consent:
                    return await self._account_data_api(password, ignore_consent=True)
            else:
                print(f"验证密码错误: {response.text}")
                raise PasswordResetRequiredError(f"验证密码错误: {response.text}")
        
        # 检查响应是否为空
        if not response.text or not response.text.strip():
            raise TwitterError("API返回空响应")
        
        # 安全解析 JSON
        try:
            resp_json = response.json()
        except Exception as e:
            raise TwitterError(f"JSON解析失败: {str(e)}")
        
        if "errors" in resp_json:
            if '/i/flow/consent_flow' in response.text:
                print("验证密码错误,需要解锁")
                await self._consent_flow_task()
                if not ignore_consent:
                    return await self._account_data_api(password, ignore_consent=True)
            else:
                errors = resp_json.get("errors", [])
                error_code = errors[0].get('code') if errors else 'unknown'
                print(f"验证密码错误,code: {error_code}")
                raise PasswordResetRequiredError(f"验证密码错误: {response.text}")
        
        if resp_json.get("status") == "ok":
            print("密码验证成功")
            self.verify = True
            
            # 获取_twitter_sess并更新到cookie
            try:
                resp_cookies = response.cookies.get_dict() if hasattr(response.cookies, 'get_dict') else dict(response.cookies)
            except:
                resp_cookies = {}
            
            if "_twitter_sess" in resp_cookies:
                twitter_sess = resp_cookies["_twitter_sess"]
                
                # 更新cookie
                cookie_dict = utils.parse_cookie_string(self.cookie)
                cookie_dict['_twitter_sess'] = twitter_sess
                new_cookie = utils.cookies_to_string(cookie_dict)
                self.session_headers["cookie"] = new_cookie
                self.session.headers["cookie"] = new_cookie
                self.cookie = new_cookie
            
            # 获取更多账号信息 (带重试)
            p13n_resp = self._session_request(
                "GET",
                'https://x.com/i/api/1.1/account/personalization/p13n_data.json',
                headers={
                    'x-csrf-token': self.csrf_token,
                    'cookie': self.cookie,
                }
            )
            if p13n_resp.text and p13n_resp.text.strip():
                try:
                    return p13n_resp.json()
                except:
                    pass
        
        return resp_json
    
    async def get_password_reset_email_hint(self, username: str = None, max_retries: int = 3) -> Dict[str, Any]:
        """
        获取找回密码时显示的脱敏邮箱 (带重试机制)
        参考: https://github.com/fa0311/TwitterFrontendFlow/blob/master/sample.py
        
        流程:
        1. 获取 guest token (未登录访问必须)
        2. password_reset_flow - 发起流程
        3. PwrJsInstrumentationSubtask - JS instrumentation
        4. PasswordResetBegin - 输入用户名
        5. PasswordResetChooseChallenge - 提取邮箱选项
        
        返回: {
            "success": bool,
            "email_hint": str or None,  # 脱敏邮箱如: q2****@t*********.***
            "error": str or None,       # 错误信息
            "retry_count": int          # 重试次数
        }
        """
        username = username or self.username
        if not username:
            return {"success": False, "email_hint": None, "error": "用户名为空", "retry_count": 0}
        
        last_error = None
        
        for retry in range(max_retries):
            reset_session = None
            try:
                result = await self._do_password_reset_email_hint(username)
                if result.get("success"):
                    result["retry_count"] = retry
                    return result
                # 非网络错误，不重试
                if not result.get("is_network_error"):
                    result["retry_count"] = retry
                    return result
                last_error = result.get("error")
                
            except Exception as e:
                last_error = str(e)
                # 判断是否网络错误
                if not self._is_network_error(last_error):
                    return {"success": False, "email_hint": None, "error": last_error, "retry_count": retry}
            
            # 网络错误，等待后重试
            if retry < max_retries - 1:
                wait_time = (retry + 1) * 2 + random.uniform(0.5, 1.5)
                print(f"网络错误，{wait_time:.1f}秒后重试 ({retry + 1}/{max_retries}): {last_error}")
                await asyncio.sleep(wait_time)
        
        return {"success": False, "email_hint": None, "error": f"重试{max_retries}次后仍失败: {last_error}", "retry_count": max_retries}
    
    def _is_network_error(self, error_msg: str) -> bool:
        """判断是否为网络错误 (兼容旧代码，调用静态方法)"""
        return self.is_network_error(error_msg)
    
    async def _do_password_reset_email_hint(self, username: str) -> Dict[str, Any]:
        """执行获取找回密码邮箱的核心逻辑"""
        reset_session = None
        
        try:
            # 1. 创建独立 session
            proxies_dict = None
            if self.proxy:
                proxies_dict = {
                    "http": self.proxy,
                    "https": self.proxy
                }
            
            reset_session = cffi_requests.Session(
                impersonate="chrome120",
                proxies=proxies_dict,
                verify=False
            )
            
            # 2. 请求页面获取 cookie (带重试)
            page_response = self._request_with_retry(
                reset_session, "GET",
                "https://x.com/i/flow/password_reset",
                headers={
                    "User-Agent": self.useragent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=30
            )
            
            # 提取 ct0
            ct0 = reset_session.cookies.get("ct0", "").strip()
            if ct0.startswith("ct0:"):
                ct0 = ct0[4:].strip()
            
            # 3. 获取 guest token (带重试)
            guest_resp = self._request_with_retry(
                reset_session, "POST",
                "https://api.x.com/1.1/guest/activate.json",
                headers={
                    "User-Agent": self.useragent,
                    "Authorization": settings.TWITTER_BEARER_TOKEN,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=30
            )
            
            guest_token = None
            if guest_resp.status_code == 200:
                guest_data = guest_resp.json()
                guest_token = guest_data.get("guest_token")
            
            if not guest_token:
                return {
                    "success": False, 
                    "email_hint": None, 
                    "error": f"获取guest_token失败: {guest_resp.text[:100]}",
                    "is_network_error": guest_resp.status_code in [502, 503, 504]
                }
            
            # 通用请求头 (使用 guest token)
            def get_headers():
                return {
                    "User-Agent": self.useragent,
                    "Accept": "*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Content-Type": "application/json",
                    "Authorization": settings.TWITTER_BEARER_TOKEN,
                    "x-guest-token": guest_token,
                    "Referer": "https://x.com/",
                    "x-twitter-active-user": "yes",
                    "x-twitter-client-language": "en",
                    "x-csrf-token": ct0,
                    "x-client-transaction-id": utils.get_tid("/1.1/onboarding/task.json"),
                }
            
            def update_ct0():
                nonlocal ct0
                new_ct0 = reset_session.cookies.get("ct0", "").strip()
                if new_ct0:
                    ct0 = new_ct0[4:].strip() if new_ct0.startswith("ct0:") else new_ct0
            
            # 4. 发起 password_reset_flow (带重试)
            await asyncio.sleep(random.uniform(0.3, 0.8))
            resp = self._request_with_retry(
                reset_session, "POST",
                "https://api.x.com/1.1/onboarding/task.json?flow_name=password_reset",
                headers=get_headers(),
                json={
                    "input_flow_data": {
                        "flow_context": {
                            "debug_overrides": {},
                            "start_location": {"location": "manual_link"}
                        }
                    },
                    "subtask_versions": {}
                },
                timeout=30
            )
            update_ct0()
            
            if resp.status_code != 200:
                return {
                    "success": False,
                    "email_hint": None,
                    "error": f"password_reset_flow失败({resp.status_code}): {resp.text[:100]}",
                    "is_network_error": resp.status_code in [502, 503, 504]
                }
            
            data = resp.json()
            flow_token = data.get("flow_token")
            subtask_ids = [s.get("subtask_id") for s in data.get("subtasks", [])]
            
            # 5. PwrJsInstrumentationSubtask (如果存在)
            if "PwrJsInstrumentationSubtask" in subtask_ids:
                await asyncio.sleep(random.uniform(0.2, 0.5))
                resp = self._request_with_retry(
                    reset_session, "POST",
                    "https://api.x.com/1.1/onboarding/task.json",
                    headers=get_headers(),
                    json={
                        "flow_token": flow_token,
                        "subtask_inputs": [{
                            "subtask_id": "PwrJsInstrumentationSubtask",
                            "js_instrumentation": {
                                "response": "{}",
                                "link": "next_link"
                            }
                        }]
                    },
                    timeout=30
                )
                update_ct0()
                
                if resp.status_code != 200:
                    return {
                        "success": False,
                        "email_hint": None,
                        "error": f"PwrJsInstrumentation失败({resp.status_code}): {resp.text[:100]}",
                        "is_network_error": resp.status_code in [502, 503, 504]
                    }
                
                data = resp.json()
                flow_token = data.get("flow_token")
                subtask_ids = [s.get("subtask_id") for s in data.get("subtasks", [])]
            
            # 6. PasswordResetBegin - 输入用户名
            if "PasswordResetBegin" in subtask_ids:
                await asyncio.sleep(random.uniform(0.3, 0.8))
                resp = self._request_with_retry(
                    reset_session, "POST",
                    "https://api.x.com/1.1/onboarding/task.json",
                    headers=get_headers(),
                    json={
                        "flow_token": flow_token,
                        "subtask_inputs": [{
                            "subtask_id": "PasswordResetBegin",
                            "enter_text": {
                                "text": username,
                                "link": "next_link"
                            }
                        }]
                    },
                    timeout=30
                )
                update_ct0()
                
                if resp.status_code != 200:
                    return {
                        "success": False,
                        "email_hint": None,
                        "error": f"PasswordResetBegin失败({resp.status_code}): {resp.text[:100]}",
                        "is_network_error": resp.status_code in [502, 503, 504]
                    }
                
                data = resp.json()
                subtask_ids = [s.get("subtask_id") for s in data.get("subtasks", [])]
            
            # 7. 从 PasswordResetChooseChallenge 提取邮箱
            for subtask in data.get("subtasks", []):
                subtask_id = subtask.get("subtask_id", "")
                
                if subtask_id == "PasswordResetChooseChallenge" or "choice_selection" in subtask:
                    choices = subtask.get("choice_selection", {}).get("choices", [])
                    for choice in choices:
                        text = choice.get("text", {})
                        if isinstance(text, dict):
                            text = text.get("text", "")
                        if isinstance(text, str) and "@" in text and "*" in text:
                            email = self._extract_pure_email(text)
                            if email:
                                return {"success": True, "email_hint": email, "error": None, "is_network_error": False}
                
                email_hint = self._extract_email_hint_from_subtask(subtask)
                if email_hint:
                    return {"success": True, "email_hint": email_hint, "error": None, "is_network_error": False}
            
            return {"success": True, "email_hint": None, "error": "未找到邮箱信息", "is_network_error": False}
            
        except Exception as e:
            error_msg = str(e)
            return {
                "success": False,
                "email_hint": None,
                "error": error_msg,
                "is_network_error": self._is_network_error(error_msg)
            }
        finally:
            if reset_session:
                try:
                    reset_session.close()
                except:
                    pass
    
    def _request_with_retry(self, session, method: str, url: str, max_retries: int = 2, **kwargs):
        """带重试的请求方法"""
        last_error = None
        for i in range(max_retries):
            try:
                if method.upper() == "GET":
                    return session.get(url, **kwargs)
                else:
                    return session.post(url, **kwargs)
            except Exception as e:
                last_error = e
                if i < max_retries - 1:
                    time.sleep(1 + i)  # 递增等待
        raise last_error
    
    def _extract_pure_email(self, text: str) -> Optional[str]:
        """从文本中提取纯邮箱部分 (去掉 'Send an email to ' 等前缀)"""
        if not text:
            return None
        # 匹配脱敏邮箱格式: xx***@xx***.*** 或 xx****@xx****.***
        match = re.search(r'[a-zA-Z0-9][a-zA-Z0-9*]+@[a-zA-Z0-9*]+\.[a-zA-Z0-9*]+', text)
        if match:
            return match.group(0)
        return None
    
    def _extract_email_hint_from_subtask(self, data: Any) -> Optional[str]:
        """从subtask数据中递归提取邮箱提示"""
        if isinstance(data, str):
            if "@" in data and "*" in data:
                # 提取纯邮箱部分
                return self._extract_pure_email(data)
        elif isinstance(data, dict):
            for value in data.values():
                result = self._extract_email_hint_from_subtask(value)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._extract_email_hint_from_subtask(item)
                if result:
                    return result
        return None
    
    async def get_account_full_info(self, username: str, password: str) -> Dict[str, Any]:
        """
        获取账号完整信息 (使用 accountData 逻辑)
        
        返回格式:
        {
            "username": str,
            "password": str,
            "follower_count": int,
            "following_count": int,
            "country": str,
            "create_year": str,
            "is_premium": bool,
            "status": str  # "正常", "冻结", "改密"
        }
        """
        self.username = username
        self.password = password
        
        # 1. 先检查是否冻结
        suspend_check = await self.check_account_suspended(username)
        if suspend_check["suspended"]:
            return {
                "username": username,
                "password": password,
                "status": "冻结",
                "message": "账号已被冻结"
            }
        
        if not suspend_check["exists"]:
            return {
                "username": username,
                "password": password,
                "status": "不存在",
                "message": "账号不存在"
            }
        
        # 2. 尝试 Token 登录获取完整信息
        try:
            # 使用 accountData 逻辑获取完整信息
            account_info = await self.account_data(password)
            
            # 提取年份
            create_year = ""
            if self.create_time:
                parts = self.create_time.split()
                if parts:
                    create_year = parts[-1]
            
            return {
                "username": username,
                "password": password,
                "follower_count": self.follower_count,
                "following_count": self.following_count,
                "country": self.country,
                "create_year": create_year,
                "is_premium": self.is_premium,
                "status": "正常"
            }
            
        except PasswordResetRequiredError as e:
            # Token 登录失败，需要检查找回密码邮箱
            return {
                "username": username,
                "password": password,
                "status": "改密",
                "message": str(e),
                "need_check_email": True  # 标记需要检查邮箱
            }
        except TwitterError as e:
            return {
                "username": username,
                "password": password,
                "status": "改密",
                "message": str(e)
            }
