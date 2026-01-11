"""
工具函数
"""
import asyncio
import re
import traceback
from http.cookies import SimpleCookie
from typing import Optional, Dict, Any
import requests

from config import settings


def extract_between(text: str, left: str, right: str) -> str:
    """提取字符串中从左标记到右标记之间的内容"""
    start = text.find(left)
    if start == -1:
        return ""
    start += len(left)
    end = text.find(right, start)
    if end == -1:
        return ""
    return text[start:end]


def cookies_to_string(cookies: dict) -> str:
    """将字典转化为cookie字符串"""
    return '; '.join([f'{name}={value}' for name, value in cookies.items()])


def parse_cookie_string(cookie_string: str) -> dict:
    """解析cookie字符串为字典，支持带或不带空格的分号分隔"""
    cookies = {}
    # 先用分号分割，再处理每个 cookie 对
    # 支持 "ct0=xxx; auth_token=yyy" 和 "ct0=xxx;auth_token=yyy" 两种格式
    import re
    cookie_pairs = re.split(r';\s*', cookie_string)
    for pair in cookie_pairs:
        pair = pair.strip()
        if not pair:
            continue
        name_value = pair.split('=', 1)
        if len(name_value) == 2:
            name, value = name_value
            cookies[name.strip()] = value.strip()
    return cookies


def extract_cookies(cookie_header: str) -> str:
    """从cookie header提取cookies"""
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    cookie_strings = []
    for morsel in cookie.values():
        cookie_strings.append(f"{morsel.key}={morsel.value}")
    return "; ".join(cookie_strings)


def extract_cookies_from_dict(cookies: dict) -> str:
    """从字典提取cookie字符串"""
    return '; '.join([f'{k}={v}' for k, v in cookies.items()])


def get_tid(path: str) -> str:
    """
    获取 Twitter Transaction ID
    
    优先使用内嵌的 TID 服务，如果未启动则回退到外部服务
    """
    # 优先尝试使用内嵌的 TID 服务
    try:
        from tid_service import get_tid_service
        tid_service = get_tid_service()
        
        if tid_service.is_running and tid_service.browser_ready:
            tid = tid_service.get_tid(path)
            if tid:
                return tid
    except Exception as e:
        # 内嵌服务不可用，继续尝试外部服务
        pass
    
    # 回退到外部 TID 服务
    url = settings.TID_SERVICE_URL
    payload = {"path": path}
    headers = {"content-type": "application/json"}
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        result = response.json()
        if result.get("success"):
            tid = result["data"]["transactionId"]
            return tid
        else:
            raise Exception(result.get('msg', 'Unknown error'))
    except Exception as e:
        raise Exception(f"获取TID失败: {str(e)}")


async def retry_async(func, *args, retries: int = 5, delay: int = 3, **kwargs) -> Optional[Any]:
    """异步重试函数"""
    for attempt in range(retries):
        try:
            result = await func(*args, **kwargs)
            return result
        except Exception as e:
            error_str = str(e)
            if "密码错误" in error_str:
                return None
            print(f"尝试失败: {e}. 这是第 {attempt + 1} 次尝试。")
            traceback.print_exc()
        await asyncio.sleep(delay)
    return None


def mask_email(email: str) -> str:
    """
    将邮箱脱敏处理
    例: q2c716@tuitegmail.com -> q2****@t*********.***
    """
    if not email or '@' not in email:
        return email
    
    parts = email.split('@')
    local = parts[0]
    domain = parts[1]
    
    # 本地部分: 保留前2个字符
    if len(local) <= 2:
        masked_local = local[0] + '*' * 4
    else:
        masked_local = local[:2] + '*' * 4
    
    # 域名部分: 保留首字母和后缀第一个点后的内容
    if '.' in domain:
        domain_parts = domain.split('.')
        masked_domain = domain_parts[0][0] + '*' * 9 + '.' + '*' * 3
    else:
        masked_domain = domain[0] + '*' * 9
    
    return f"{masked_local}@{masked_domain}"


def compare_masked_email(original_email: str, masked_email: str) -> bool:
    """
    比较原始邮箱和脱敏邮箱是否匹配
    例: q2c716@tuitegmail.com 匹配 q2****@t*********.***
    
    匹配逻辑:
    1. 本地部分: 原始邮箱需要以脱敏邮箱的可见字符开头
    2. 域名部分: 原始域名需要以脱敏域名的可见字符开头
    """
    if not original_email or not masked_email:
        return False
    
    original_email = original_email.lower().strip()
    masked_email = masked_email.lower().strip()
    
    if '@' not in original_email or '@' not in masked_email:
        return False
    
    # 提取本地部分和域名
    orig_parts = original_email.split('@')
    mask_parts = masked_email.split('@')
    
    orig_local = orig_parts[0]
    orig_domain = orig_parts[1]
    
    mask_local = mask_parts[0]
    mask_domain = mask_parts[1]
    
    # 提取脱敏邮箱本地部分的可见字符（去除*号）
    # 例: q2**** -> q2
    visible_local = ""
    for char in mask_local:
        if char != '*':
            visible_local += char
        else:
            break  # 遇到*号停止
    
    # 检查本地部分前缀是否匹配
    if visible_local and not orig_local.startswith(visible_local):
        return False
    
    # 提取脱敏邮箱域名部分的可见字符
    # 例: t*********.***.*** -> t (只取第一个可见字符或连续可见字符)
    visible_domain_prefix = ""
    for char in mask_domain:
        if char != '*' and char != '.':
            visible_domain_prefix += char
        elif char == '*':
            break  # 遇到*号停止
        elif char == '.':
            break  # 遇到.号也停止
    
    # 检查域名首字符是否匹配
    if visible_domain_prefix and not orig_domain.startswith(visible_domain_prefix):
        return False
    
    # 如果都通过了检查，认为匹配
    return True


def extract_visible_from_masked(masked_str: str) -> str:
    """
    从脱敏字符串中提取可见字符
    例: q2**** -> q2
    例: t*********.***.*** -> t
    """
    result = ""
    for char in masked_str:
        if char == '*':
            break
        result += char
    return result


def parse_proxy(proxy_str: str, default_protocol: str = "socks5") -> Optional[str]:
    """
    解析代理字符串，支持多种格式：
    - host:port
    - username:password@host:port
    - username:password:host:port
    - http://... 或 socks5://... (完整URL格式)
    
    Args:
        proxy_str: 代理字符串
        default_protocol: 默认协议，默认使用 socks5
    
    返回格式化的代理URL
    """
    if not proxy_str or proxy_str.strip() == "":
        return None
    
    proxy_str = proxy_str.strip()
    
    # 如果已经是完整的URL格式，保持原样
    if proxy_str.startswith('socks5h://'):
        return proxy_str.replace('socks5h://', 'socks5://', 1)
    if proxy_str.startswith('socks5://'):
        return proxy_str
    if proxy_str.startswith('http://') or proxy_str.startswith('https://'):
        return proxy_str
    
    # 尝试解析 username:password:host:port 格式
    # 默认使用 SOCKS5 代理
    parts = proxy_str.split(':')
    
    if len(parts) == 4:
        # username:password:host:port
        username, password, host, port = parts
        return f"{default_protocol}://{username}:{password}@{host}:{port}"
    elif len(parts) == 2:
        # host:port
        host, port = parts
        return f"{default_protocol}://{host}:{port}"
    elif '@' in proxy_str:
        # username:password@host:port
        auth, location = proxy_str.split('@', 1)
        return f"{default_protocol}://{auth}@{location}"
    else:
        # 无法识别的格式，直接返回
        return f"{default_protocol}://{proxy_str}"


def extract_ct0(cookie: str) -> str:
    """从cookie中提取ct0"""
    match = re.search(r'ct0=([^;]+)', cookie)
    if match:
        ct0 = match.group(1).strip()
        # 如果 ct0 值带有 "ct0:" 前缀，去掉它
        if ct0.startswith("ct0:"):
            ct0 = ct0[4:].strip()
        return ct0
    return ''


def extract_auth_token(cookie: str) -> str:
    """从cookie中提取auth_token"""
    matches = re.findall(r'auth_token=([^;]+)', cookie)
    return matches[-1] if matches else ''


def extract_twid(cookie: str) -> str:
    """从cookie中提取twid"""
    match = re.search(r'twid=([^;]+)', cookie)
    return match.group(1) if match else ''


def extract_user_id_from_twid(twid: str) -> str:
    """从twid中提取用户ID"""
    if not twid:
        return ""
    match = re.search(r'\d+', twid)
    return match.group() if match else ""

