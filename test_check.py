#!/usr/bin/env python3
"""
单个账号检测测试脚本
从 XLS 文件读取账号，选择指定账号进行测试

检测流程:
1. 检查账号是否冻结
2. 未冻结 -> Token登录获取完整信息 (accountData逻辑)
3. Token登录失败 -> 找回密码检查邮箱
4. 邮箱不匹配 -> 标记改密

返回格式: 用户名----密码----2FA----邮箱----邮箱密码----粉丝数量----国家----年份----是否会员

用法:
    python test_check.py <xls文件> [账号索引或用户名]
    
示例:
    python test_check.py accounts.xlsx           # 列出所有账号
    python test_check.py accounts.xlsx 0         # 测试第1个账号
    python test_check.py accounts.xlsx 5         # 测试第6个账号
    python test_check.py accounts.xlsx elonmusk  # 测试指定用户名
"""
import asyncio
import sys
import json
from datetime import datetime
from pathlib import Path

# 尝试导入 Excel 读取库
try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    import xlrd
except ImportError:
    xlrd = None

if not openpyxl and not xlrd:
    print("❌ 请先安装 Excel 读取库: pip install openpyxl xlrd")
    sys.exit(1)

# 导入项目模块
from twitter_client import TwitterClient
from utils import parse_proxy, compare_masked_email


# ============ 固定配置 ============
# 远程代理
REMOTE_PROXY = "x_yaseceo-zone-resi-region-jp:QQqq123123@ee982c1739054430.iuy.us.ip2world.vip:6001"
# macOS 本地代理 (Clash等)
LOCAL_PROXY = "127.0.0.1:7897"

def get_default_proxy():
    return REMOTE_PROXY
    """根据系统自动选择代理"""
    import platform
    import subprocess
    
    if platform.system() == "Darwin":  # macOS
        try:
            # 检查是否有本地代理运行
            result = subprocess.run(['scutil', '--proxy'], capture_output=True, text=True)
            if 'HTTPProxy : 127.0.0.1' in result.stdout and 'HTTPPort : 7897' in result.stdout:
                print(f"✓ 检测到 macOS 本地代理: {LOCAL_PROXY}")
                return LOCAL_PROXY
        except:
            pass
    
    # 默认使用远程代理
    return REMOTE_PROXY

DEFAULT_PROXY = get_default_proxy()


def print_colored(text: str, color: str = ""):
    """彩色打印"""
    colors = {
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "cyan": "\033[96m",
        "reset": "\033[0m"
    }
    c = colors.get(color, "")
    r = colors["reset"]
    print(f"{c}{text}{r}")


def print_result(title: str, data: dict, color: str = ""):
    """格式化打印结果"""
    colors = {
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "reset": "\033[0m"
    }
    c = colors.get(color, "")
    r = colors["reset"]
    
    print(f"\n{c}{'='*50}")
    print(f" {title}")
    print(f"{'='*50}{r}")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def load_accounts_from_xlsx(file_path: str) -> list:
    """
    从 Excel 文件加载账号 (支持 .xlsx 和 .xls 格式)
    
    预期列顺序:
    账号 | 密码 | 2fa | ct0 | authtoken | 邮箱账号 | 邮箱密码 | 粉丝数量 | 国家 | 年份 | 是否会员
    """
    accounts = []
    file_ext = Path(file_path).suffix.lower()
    
    # 根据文件格式选择读取方式
    if file_ext == '.xls':
        # 使用 xlrd 读取旧格式
        if not xlrd:
            print("❌ 读取 .xls 文件需要安装 xlrd: pip install xlrd")
            sys.exit(1)
        
        wb = xlrd.open_workbook(file_path)
        ws = wb.sheet_by_index(0)
        
        # 跳过表头，从第2行开始
        for row_idx in range(1, ws.nrows):
            row = [ws.cell_value(row_idx, col) for col in range(ws.ncols)]
            account = _parse_row(row, row_idx - 1)
            if account:
                accounts.append(account)
    else:
        # 使用 openpyxl 读取新格式
        if not openpyxl:
            print("❌ 读取 .xlsx 文件需要安装 openpyxl: pip install openpyxl")
            sys.exit(1)
        
        wb = openpyxl.load_workbook(file_path, read_only=True)
        ws = wb.active
        
        # 跳过表头
        rows = list(ws.iter_rows(min_row=2, values_only=True))
        
        for idx, row in enumerate(rows):
            account = _parse_row(row, idx)
            if account:
                accounts.append(account)
        
        wb.close()
    
    return accounts


def _parse_row(row, idx: int) -> dict:
    """解析单行数据"""
    if not row or not row[0]:  # 跳过空行
        return None
        
    # 构建 cookie
    ct0 = str(row[3]) if len(row) > 3 and row[3] else ""
    auth_token = str(row[4]) if len(row) > 4 and row[4] else ""
    cookie = ""
    if ct0:
        cookie += f"ct0={ct0};"
    if auth_token:
        cookie += f"auth_token={auth_token};"
    
    # 处理粉丝数量（可能是浮点数）
    follower_count = 0
    if len(row) > 7 and row[7]:
        try:
            follower_count = int(float(row[7]))
        except (ValueError, TypeError):
            pass
    
    account = {
        "index": idx,
        "username": str(row[0]).strip() if row[0] else "",
        "password": str(row[1]).strip() if len(row) > 1 and row[1] else "",
        "two_fa": str(row[2]).strip() if len(row) > 2 and row[2] else "",
        "ct0": ct0,
        "auth_token": auth_token,
        "cookie": cookie,
        "email": str(row[5]).strip() if len(row) > 5 and row[5] else "",
        "email_password": str(row[6]).strip() if len(row) > 6 and row[6] else "",
        "follower_count": follower_count,
        "country": str(row[8]).strip() if len(row) > 8 and row[8] else "",
        "create_year": str(row[9]).strip() if len(row) > 9 and row[9] else "",
        "is_premium": bool(row[10]) if len(row) > 10 and row[10] else False,
    }
    
    if account["username"]:
        return account
    return None


def list_accounts(accounts: list):
    """列出所有账号"""
    print_colored("\n📋 账号列表:", "cyan")
    print("-" * 80)
    print(f"{'序号':<6} {'用户名':<20} {'密码':<15} {'Cookie':<10} {'粉丝':<10}")
    print("-" * 80)
    
    for acc in accounts:
        has_cookie = "✓" if acc["cookie"] else "✗"
        pwd_display = acc["password"][:10] + "..." if len(acc["password"]) > 10 else acc["password"]
        print(f"{acc['index']:<6} @{acc['username']:<19} {pwd_display:<15} {has_cookie:<10} {acc['follower_count']:<10}")
    
    print("-" * 80)
    print(f"共 {len(accounts)} 个账号")
    print("\n使用方法: python test_check.py <文件> <序号或用户名>")


async def check_single_account(
    account: dict,
    proxy: str = DEFAULT_PROXY,
    verbose: bool = True
) -> dict:
    """
    检测单个账号 (完整流程)
    
    流程:
    1. 检查账号是否冻结
    2. 未冻结 -> Token登录获取完整信息 (accountData逻辑)
    3. Token登录失败 -> 找回密码检查邮箱
    4. 邮箱不匹配 -> 标记改密
    
    Args:
        account: 账号信息字典
        proxy: 代理地址
        verbose: 是否打印详细日志
    
    Returns:
        检测结果字典
    """
    username = account["username"]
    password = account.get("password", "")
    cookie = account.get("cookie", "")
    email = account.get("email", "")
    
    result = {
        "username": username,
        "password": password,
        "two_fa": account.get("two_fa", ""),
        "email": email,
        "email_password": account.get("email_password", ""),
        "status": "未知",
        "status_message": "",
        "follower_count": 0,
        "following_count": 0,
        "country": "",
        "create_year": "",
        "is_premium": False,
        "checked_at": datetime.now().isoformat()
    }
    
    try:
        # 解析代理
        parsed_proxy = parse_proxy(proxy) if proxy else None
        
        if verbose:
            print_colored(f"\n🔍 开始检测账号: @{username}", "cyan")
            print(f"   密码: {password[:5]}***" if password else "   密码: 无")
        
        # 创建客户端
        client = TwitterClient(
            cookie=cookie,
            proxy=parsed_proxy,
            password=password
        )
        client.username = username
        
        if verbose:
            print(f"   csrf_token: {client.csrf_token[:30]}..." if client.csrf_token else "   csrf_token: 无")
        
        # ========== 步骤1: 检测是否冻结 ==========
        if verbose:
            print(f"\n📋 步骤1: 检测账号状态...")
        
        suspend_result = await client.check_account_suspended(username)
        
        if verbose:
            print_result("冻结检测结果", suspend_result, "blue")
        
        if suspend_result.get("suspended"):
            result["status"] = "冻结"
            result["status_message"] = "账号已被冻结"
            if verbose:
                print_result("❌ 检测结果: 账号已冻结", result, "red")
                print_export_format(result)
            return result
        
        # 检查是否是网络错误 (exists 为 None)
        if suspend_result.get("error") and suspend_result.get("exists") is None:
            result["status"] = "网络错误"
            result["status_message"] = suspend_result.get("message", "网络错误，需重试")
            if verbose:
                print_result("⚠️ 检测结果: 网络错误，需重试", result, "yellow")
            return result
        
        # 账号不存在 (exists 明确为 False)
        if suspend_result.get("exists") is False:
            result["status"] = "不存在"
            result["status_message"] = suspend_result.get("message", "账号不存在")
            if verbose:
                print_result("❌ 检测结果: 账号不存在", result, "red")
            return result
        
        # ========== 步骤2: Token登录获取完整信息 (accountData逻辑) ==========
        if cookie:
            if verbose:
                print(f"\n📋 步骤2: Token登录获取完整信息 (accountData)...")
            
            try:
                # 使用 accountData 逻辑获取完整信息
                account_info = await client.account_data(password)
                
                if verbose:
                    print_result("accountData 结果", account_info, "blue")
                
                # 更新结果
                result["follower_count"] = client.follower_count
                result["following_count"] = client.following_count
                result["country"] = client.country
                result["is_premium"] = client.is_premium
                
                # 解析创建年份
                if client.create_time:
                    result["created_at_raw"] = client.create_time
                    parts = client.create_time.split()
                    result["create_year"] = parts[-1] if parts else ""
                
                result["status"] = "正常"
                result["status_message"] = "账号正常"
                
                if verbose:
                    print_result("✅ 检测结果: 账号正常", result, "green")
                    print_export_format(result)
                    
                return result
                
            except Exception as e:
                error_msg = str(e)
                if verbose:
                    print_colored(f"\n⚠️ Token登录失败: {error_msg[:100]}", "yellow")
                
                # Token登录失败，继续检查找回密码邮箱
        else:
            if verbose:
                print_colored(f"\n⚠️ 无Cookie，跳过Token登录", "yellow")
        
        # ========== 步骤3: 找回密码检查邮箱 ==========
        if verbose:
            print(f"\n📋 步骤3: 检查找回密码邮箱...")
        
        try:
            email_result = await client.get_password_reset_email_hint(username)
            masked_email = email_result.get("email_hint") if email_result.get("success") else None
            
            if verbose:
                print(f"   找回密码显示的邮箱: {masked_email or '无法获取'}")
                if email_result.get("retry_count", 0) > 0:
                    print(f"   (重试了 {email_result.get('retry_count')} 次)")
            
            if not masked_email:
                # 区分网络错误和其他错误
                if email_result.get("is_network_error") or "重试" in str(email_result.get("error", "")):
                    result["status"] = "错误"
                    result["status_message"] = f"网络错误: {email_result.get('error', '未知')}"
                else:
                    result["status"] = "改密"
                    result["status_message"] = email_result.get("error") or "无法获取找回密码邮箱提示"
                if verbose:
                    status_type = "错误" if result["status"] == "错误" else "改密"
                    print_result(f"⚠️ 检测结果: {status_type} ({result['status_message'][:50]})", result, "yellow")
                    print_export_format(result)
                return result
            
            # 步骤4: 比较邮箱是否匹配
            if email:
                if verbose:
                    print(f"   期望邮箱: {email}")
                    print(f"   实际邮箱: {masked_email}")
                
                if compare_masked_email(email, masked_email):
                    # 邮箱匹配，但Token登录失败
                    result["status"] = "改密"
                    result["status_message"] = f"邮箱匹配({masked_email})，但登录失败需改密"
                    if verbose:
                        print_colored(f"   ✓ 邮箱匹配!", "green")
                        print_result("⚠️ 检测结果: 邮箱匹配但需改密", result, "yellow")
                else:
                    # 邮箱不匹配
                    result["status"] = "改密"
                    result["status_message"] = f"邮箱不匹配！期望:{email}, 实际:{masked_email}"
                    if verbose:
                        print_colored(f"   ✗ 邮箱不匹配!", "red")
                        print_result("❌ 检测结果: 邮箱不匹配，改密", result, "red")
            else:
                # 没有提供期望邮箱
                result["status"] = "改密"
                result["status_message"] = f"找回密码邮箱: {masked_email}"
                if verbose:
                    print_result("⚠️ 检测结果: 改密", result, "yellow")
            
            if verbose:
                print_export_format(result)
                
        except Exception as e:
            result["status"] = "改密"
            result["status_message"] = f"检查找回密码失败: {str(e)[:100]}"
            if verbose:
                print_colored(f"\n⚠️ 检查找回密码异常: {str(e)}", "yellow")
                print_result("⚠️ 检测结果: 改密", result, "yellow")
                print_export_format(result)
                
    except Exception as e:
        result["status"] = "错误"
        result["status_message"] = str(e)[:200]
        if verbose:
            print_result("❌ 检测异常", {"error": str(e)}, "red")
    
    return result


def print_export_format(result: dict):
    """打印导出格式"""
    premium_str = "会员" if result.get("is_premium") else "普通用户"
    export_line = (
        f"{result.get('username', '')}----"
        f"{result.get('password', '')}----"
        f"{result.get('two_fa', '')}----"
        f"{result.get('email', '')}----"
        f"{result.get('email_password', '')}----"
        f"{result.get('follower_count', 0)}----"
        f"{result.get('country', '')}----"
        f"{result.get('create_year', '')}----"
        f"{premium_str}"
    )
    print_colored(f"\n📤 导出格式:", "cyan")
    print(f"   {export_line}")


def main():
    print_colored("\n" + "="*60, "cyan")
    print_colored(" Twitter 账号检测测试工具", "cyan")
    print_colored("="*60, "cyan")
    print(f" 固定代理: {DEFAULT_PROXY}")
    print("="*60)
    
    # 检查参数
    if len(sys.argv) < 2:
        print("\n用法: python test_check.py <xls文件> [账号索引或用户名]")
        print("\n示例:")
        print("  python test_check.py accounts.xlsx           # 列出所有账号")
        print("  python test_check.py accounts.xlsx 0         # 测试第1个账号")
        print("  python test_check.py accounts.xlsx elonmusk  # 测试指定用户名")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    # 检查文件是否存在
    if not Path(file_path).exists():
        print_colored(f"\n❌ 文件不存在: {file_path}", "red")
        sys.exit(1)
    
    # 加载账号
    print(f"\n📂 正在加载账号文件: {file_path}")
    accounts = load_accounts_from_xlsx(file_path)
    
    if not accounts:
        print_colored("\n❌ 未找到任何账号", "red")
        sys.exit(1)
    
    print_colored(f"✓ 已加载 {len(accounts)} 个账号", "green")
    
    # 如果没有指定账号，列出所有
    if len(sys.argv) < 3:
        list_accounts(accounts)
        sys.exit(0)
    
    # 查找指定账号
    target = sys.argv[2]
    account = None
    
    # 尝试按索引查找
    try:
        idx = int(target)
        if 0 <= idx < len(accounts):
            account = accounts[idx]
        else:
            print_colored(f"\n❌ 索引超出范围: {idx} (共 {len(accounts)} 个账号)", "red")
            sys.exit(1)
    except ValueError:
        # 按用户名查找
        for acc in accounts:
            if acc["username"].lower() == target.lower():
                account = acc
                break
        
        if not account:
            print_colored(f"\n❌ 未找到用户名: {target}", "red")
            sys.exit(1)
    
    # 显示账号信息
    print_colored(f"\n📌 选中账号:", "cyan")
    print(f"   序号: {account['index']}")
    print(f"   用户名: @{account['username']}")
    print(f"   密码: {account['password'][:5]}***")
    print(f"   2FA: {'有' if account['two_fa'] else '无'}")
    print(f"   Cookie: {'有' if account['cookie'] else '无'}")
    
    # 检查是否禁用代理 (第三个参数 --no-proxy 或 -n)
    use_proxy = True
    if len(sys.argv) > 3 and sys.argv[3] in ['--no-proxy', '-n']:
        use_proxy = False
        print_colored("⚠️ 已禁用代理", "yellow")
    
    # 运行检测
    result = asyncio.run(check_single_account(
        account=account,
        proxy=DEFAULT_PROXY if use_proxy else None,
        verbose=True
    ))
    
    print_colored("\n" + "="*60, "cyan")
    print_colored(" 检测完成", "cyan")
    print_colored("="*60 + "\n", "cyan")
    
    # 返回状态码
    if result.get("status") == "正常":
        return 0
    elif result.get("status") in ["冻结", "改密"]:
        return 1
    else:
        return 2


if __name__ == "__main__":
    exit(main())
