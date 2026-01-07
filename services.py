"""
账号服务层
提供账号检测、分类、提取等核心业务逻辑
"""
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import TwitterAccount, AccountStatus, CheckTask
from twitter_client import TwitterClient
from exceptions import TwitterError
import utils


class AccountService:
    """账号服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ==================== 账号检测 ====================
    
    async def check_single_account(
        self,
        username: str,
        password: str,
        two_fa: Optional[str] = None,
        email: Optional[str] = None,
        email_password: Optional[str] = None,
        cookie: Optional[str] = None,
        proxy: Optional[str] = None
    ) -> TwitterAccount:
        """
        检测单个账号
        
        流程:
        1. x.com/用户名 查询是否冻结
        2. 未冻结则使用Token登陆获取粉丝数量等信息 (accountData逻辑)
        3. Token登陆失败则检查找回密码邮箱是否匹配
        4. 邮箱不匹配则标记为改密
        
        返回格式: 用户名----密码----2FA----邮箱----邮箱密码----粉丝数量----国家----年份----是否会员
        """
        # 查找或创建账号记录
        account = await self._get_or_create_account(username, password)
        account.two_fa = two_fa
        account.email = email
        account.email_password = email_password
        account.cookie = cookie
        
        try:
            # 创建客户端
            client = TwitterClient(
                cookie=cookie or "",
                proxy=proxy,
                password=password
            )
            client.username = username
            
            # 1. 检查是否冻结
            suspend_result = await client.check_account_suspended(username)
            
            if suspend_result["suspended"]:
                account.status = AccountStatus.SUSPENDED.value
                account.status_message = "账号已被冻结"
                account.checked_at = datetime.utcnow()
                await self.db.commit()
                return account
            
            # 检查是否是网络错误 (exists 为 None)
            if suspend_result.get("error") and suspend_result.get("exists") is None:
                error_msg = suspend_result.get("message", "网络错误")
                account.status = AccountStatus.ERROR.value
                account.status_message = error_msg
                account.checked_at = datetime.utcnow()
                await self.db.commit()
                return account
            
            # 账号不存在 (exists 明确为 False)
            if suspend_result.get("exists") is False:
                account.status = AccountStatus.NOT_FOUND.value
                account.status_message = "账号不存在"
                account.checked_at = datetime.utcnow()
                await self.db.commit()
                return account
            
            # 2. 未冻结，尝试Token登录获取完整信息
            if cookie:
                try:
                    # 使用 accountData 逻辑获取完整信息
                    account_info = await client.account_data(password)
                    
                    # 更新账号信息
                    account.follower_count = client.follower_count
                    account.following_count = client.following_count
                    account.country = client.country
                    account.is_premium = client.is_premium
                    
                    # 提取年份
                    if client.create_time:
                        parts = client.create_time.split()
                        if parts:
                            account.create_year = parts[-1]
                    
                    # 更新cookie
                    account.cookie = client.cookie
                    account.auth_token = utils.extract_auth_token(client.cookie)
                    
                    account.status = AccountStatus.NORMAL.value
                    account.status_message = "账号正常"
                    account.checked_at = datetime.utcnow()
                    
                except TwitterError as e:
                    # Token登录失败，检查是否需要改密
                    account = await self._check_password_reset(
                        account, client, email
                    )
            else:
                # 没有cookie，检查找回密码邮箱
                account = await self._check_password_reset(
                    account, client, email
                )
            
            await self.db.commit()
            return account
            
        except Exception as e:
            account.status = AccountStatus.ERROR.value
            account.status_message = f"检测错误: {str(e)}"
            account.checked_at = datetime.utcnow()
            await self.db.commit()
            return account
    
    async def _check_password_reset(
        self,
        account: TwitterAccount,
        client: TwitterClient,
        expected_email: Optional[str]
    ) -> TwitterAccount:
        """
        检查找回密码邮箱是否匹配
        
        流程:
        1. Token登陆失败时，发起找回密码流程
        2. 获取显示的脱敏邮箱（如: q2****@t*********.***）
        3. 与期望邮箱比较（如: q2c716@tuitegmail.com）
        4. 不匹配则标记为改密
        """
        try:
            # 获取找回密码显示的脱敏邮箱 (带重试机制)
            email_result = await client.get_password_reset_email_hint(account.username)
            masked_email = email_result.get("email_hint") if email_result.get("success") else None
            
            if not masked_email:
                # 区分网络错误和其他错误
                if email_result.get("is_network_error") or "重试" in str(email_result.get("error", "")):
                    account.status = AccountStatus.ERROR.value
                    account.status_message = f"网络错误: {email_result.get('error', '未知')[:100]}"
                else:
                    account.status = AccountStatus.RESET_PWD.value
                    account.status_message = email_result.get("error") or "无法获取找回密码邮箱提示"
                account.checked_at = datetime.utcnow()
                return account
            
            if expected_email:
                # 比较邮箱是否匹配
                # 例: q2c716@tuitegmail.com 应该匹配 q2****@t*********.***
                if utils.compare_masked_email(expected_email, masked_email):
                    # 邮箱匹配，但Token登录仍然失败，标记为改密
                    account.status = AccountStatus.RESET_PWD.value
                    account.status_message = f"邮箱匹配({masked_email})，但需要改密"
                else:
                    # 邮箱不匹配，标记为改密
                    account.status = AccountStatus.RESET_PWD.value
                    account.status_message = f"邮箱不匹配！期望:{expected_email}, 实际:{masked_email}"
            else:
                # 没有提供期望邮箱，直接标记为改密
                account.status = AccountStatus.RESET_PWD.value
                account.status_message = f"找回密码邮箱: {masked_email}"
            
            account.checked_at = datetime.utcnow()
            
        except Exception as e:
            account.status = AccountStatus.ERROR.value
            account.status_message = f"检查找回密码失败: {str(e)[:100]}"
            account.checked_at = datetime.utcnow()
        
        return account
    
    async def _get_or_create_account(
        self, 
        username: str, 
        password: str
    ) -> TwitterAccount:
        """获取或创建账号记录"""
        stmt = select(TwitterAccount).where(
            TwitterAccount.username == username
        )
        result = await self.db.execute(stmt)
        account = result.scalar_one_or_none()
        
        if not account:
            account = TwitterAccount(
                username=username,
                password=password
            )
            self.db.add(account)
            await self.db.flush()
        else:
            account.password = password
        
        return account
    
    async def batch_import_accounts(
        self,
        accounts_data: List[Dict[str, Any]]
    ) -> int:
        """
        批量导入账号 - 使用批量 upsert 优化性能
        
        返回导入的账号数量
        """
        if not accounts_data:
            return 0
        
        # 获取所有 username
        usernames = [acc.get("username") for acc in accounts_data if acc.get("username")]
        
        # 一次性查询所有已存在的账号
        stmt = select(TwitterAccount).where(TwitterAccount.username.in_(usernames))
        result = await self.db.execute(stmt)
        existing_accounts = {acc.username: acc for acc in result.scalars().all()}
        
        new_accounts = []
        for data in accounts_data:
            username = data.get("username")
            if not username:
                continue
            
            if username in existing_accounts:
                # 更新已存在的账号
                account = existing_accounts[username]
                account.password = data.get("password", account.password)
                if data.get("two_fa"):
                    account.two_fa = data["two_fa"]
                if data.get("cookie"):
                    account.cookie = data["cookie"]
                if data.get("auth_token"):
                    account.auth_token = data["auth_token"]
                if data.get("email"):
                    account.email = data["email"]
                if data.get("email_password"):
                    account.email_password = data["email_password"]
                if data.get("follower_count"):
                    account.follower_count = data["follower_count"]
                if data.get("country"):
                    account.country = data["country"]
                if data.get("create_year"):
                    account.create_year = data["create_year"]
                if data.get("is_premium") is not None:
                    account.is_premium = data["is_premium"]
            else:
                # 创建新账号
                account = TwitterAccount(
                    username=username,
                    password=data.get("password", ""),
                    two_fa=data.get("two_fa"),
                    cookie=data.get("cookie"),
                    auth_token=data.get("auth_token"),
                    email=data.get("email"),
                    email_password=data.get("email_password"),
                    follower_count=data.get("follower_count", 0),
                    country=data.get("country"),
                    create_year=data.get("create_year"),
                    is_premium=data.get("is_premium", False),
                )
                new_accounts.append(account)
        
        # 批量添加新账号
        if new_accounts:
            self.db.add_all(new_accounts)
        
        await self.db.commit()
        return len(accounts_data)
    
    async def batch_check_accounts(
        self,
        accounts_data: List[Dict[str, Any]],
        proxy: Optional[str] = None,
        concurrency: int = 5
    ) -> CheckTask:
        """
        批量检测账号
        
        accounts_data 格式:
        [
            {
                "username": "xxx",
                "password": "xxx",
                "two_fa": "xxx",       # 可选
                "email": "xxx",         # 可选
                "email_password": "xxx", # 可选
                "cookie": "xxx"         # 可选
            },
            ...
        ]
        """
        # 创建检测任务
        task = CheckTask(
            total_count=len(accounts_data),
            status="running",
            started_at=datetime.utcnow()
        )
        self.db.add(task)
        await self.db.commit()
        
        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(concurrency)
        
        async def check_with_semaphore(account_data: Dict[str, Any]):
            async with semaphore:
                try:
                    result = await self.check_single_account(
                        username=account_data.get("username", ""),
                        password=account_data.get("password", ""),
                        two_fa=account_data.get("two_fa"),
                        email=account_data.get("email"),
                        email_password=account_data.get("email_password"),
                        cookie=account_data.get("cookie"),
                        proxy=proxy
                    )
                    
                    # 更新任务计数
                    task.processed_count += 1
                    if result.status == AccountStatus.NORMAL.value:
                        task.success_count += 1
                    elif result.status == AccountStatus.SUSPENDED.value:
                        task.suspended_count += 1
                    elif result.status == AccountStatus.RESET_PWD.value:
                        task.reset_pwd_count += 1
                    else:
                        task.error_count += 1
                    
                    await self.db.commit()
                    return result
                    
                except Exception as e:
                    task.processed_count += 1
                    task.error_count += 1
                    await self.db.commit()
                    return None
        
        # 并发执行检测
        tasks = [check_with_semaphore(data) for data in accounts_data]
        await asyncio.gather(*tasks)
        
        # 更新任务状态
        task.status = "completed"
        task.completed_at = datetime.utcnow()
        await self.db.commit()
        
        return task
    
    # ==================== 账号分类 ====================
    
    async def get_accounts_by_status(
        self,
        status: str,
        page: int = 1,
        page_size: int = 100,
        is_extracted: Optional[bool] = None
    ) -> Tuple[List[TwitterAccount], int]:
        """按状态获取账号"""
        # 构建条件
        conditions = [TwitterAccount.status == status]
        if is_extracted is not None:
            conditions.append(TwitterAccount.is_extracted == is_extracted)
        
        # 获取总数
        count_stmt = select(func.count()).select_from(TwitterAccount).where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar()
        
        # 获取分页数据
        offset = (page - 1) * page_size
        stmt = (
            select(TwitterAccount)
            .where(and_(*conditions))
            .offset(offset)
            .limit(page_size)
            .order_by(TwitterAccount.id.desc())
        )
        result = await self.db.execute(stmt)
        accounts = result.scalars().all()
        
        return list(accounts), total
    
    async def get_accounts_by_country(
        self,
        country: str,
        page: int = 1,
        page_size: int = 100,
        is_extracted: Optional[bool] = None
    ) -> Tuple[List[TwitterAccount], int]:
        """按国家获取账号"""
        # 构建条件
        conditions = [
            TwitterAccount.country == country,
            TwitterAccount.status == AccountStatus.NORMAL.value
        ]
        if is_extracted is not None:
            conditions.append(TwitterAccount.is_extracted == is_extracted)
        
        count_stmt = select(func.count()).select_from(TwitterAccount).where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar()
        
        offset = (page - 1) * page_size
        stmt = (
            select(TwitterAccount)
            .where(and_(*conditions))
            .offset(offset)
            .limit(page_size)
            .order_by(TwitterAccount.follower_count.desc())
        )
        result = await self.db.execute(stmt)
        accounts = result.scalars().all()
        
        return list(accounts), total
    
    async def get_accounts_by_follower_range(
        self,
        min_followers: int = 0,
        max_followers: int = 999999999,
        page: int = 1,
        page_size: int = 100,
        is_extracted: Optional[bool] = None
    ) -> Tuple[List[TwitterAccount], int]:
        """按粉丝数量范围获取账号"""
        # 构建条件
        conditions = [
            TwitterAccount.follower_count >= min_followers,
            TwitterAccount.follower_count <= max_followers,
            TwitterAccount.status == AccountStatus.NORMAL.value
        ]
        if is_extracted is not None:
            conditions.append(TwitterAccount.is_extracted == is_extracted)
        
        count_stmt = select(func.count()).select_from(TwitterAccount).where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar()
        
        offset = (page - 1) * page_size
        stmt = (
            select(TwitterAccount)
            .where(and_(*conditions))
            .offset(offset)
            .limit(page_size)
            .order_by(TwitterAccount.follower_count.desc())
        )
        result = await self.db.execute(stmt)
        accounts = result.scalars().all()
        
        return list(accounts), total
    
    async def get_country_statistics(self) -> List[Dict[str, Any]]:
        """获取国家统计"""
        stmt = (
            select(
                TwitterAccount.country,
                func.count(TwitterAccount.id).label('count')
            )
            .where(TwitterAccount.status == AccountStatus.NORMAL.value)
            .group_by(TwitterAccount.country)
            .order_by(func.count(TwitterAccount.id).desc())
        )
        result = await self.db.execute(stmt)
        rows = result.all()
        
        return [
            {"country": row.country or "未知", "count": row.count}
            for row in rows
        ]
    
    async def get_follower_range_statistics(self) -> List[Dict[str, Any]]:
        """获取粉丝数量区间统计 - 使用单条 SQL 查询优化性能"""
        from sqlalchemy import case, literal
        
        ranges = [
            (0, 9, "0-9"),
            (10, 99, "10-99"),
            (100, 999, "100-999"),
            (1000, 9999, "1K-10K"),
            (10000, 99999, "10K-100K"),
            (100000, 999999, "100K-1M"),
            (1000000, 999999999, "1M+"),
        ]
        
        # 使用 CASE WHEN 一次性获取所有区间统计
        case_conditions = []
        for min_val, max_val, label in ranges:
            case_conditions.append(
                func.sum(
                    case(
                        (and_(
                            TwitterAccount.follower_count >= min_val,
                            TwitterAccount.follower_count <= max_val
                        ), 1),
                        else_=0
                    )
                ).label(f"range_{min_val}_{max_val}")
            )
        
        stmt = select(*case_conditions).select_from(TwitterAccount).where(
            TwitterAccount.status == AccountStatus.NORMAL.value
        )
        
        result = await self.db.execute(stmt)
        row = result.one()
        
        statistics = []
        for i, (min_val, max_val, label) in enumerate(ranges):
            statistics.append({
                "range": label,
                "min": min_val,
                "max": max_val,
                "count": row[i] or 0
            })
        
        return statistics
    
    # ==================== 账号提取 ====================
    
    async def extract_accounts(
        self,
        country: Optional[str] = None,
        min_followers: int = 0,
        max_followers: int = 999999999,
        limit: int = 100,
        status: str = AccountStatus.NORMAL.value,
        mark_extracted: bool = True
    ) -> List[TwitterAccount]:
        """
        提取账号
        
        例: 日本，粉丝数量：0-9个，提取100个
        
        只提取未提取过的账号，提取后自动标记
        """
        conditions = [
            TwitterAccount.status == status,
            TwitterAccount.is_extracted == False  # 只提取未提取过的
        ]
        
        if country:
            conditions.append(TwitterAccount.country == country)
        
        conditions.append(TwitterAccount.follower_count >= min_followers)
        conditions.append(TwitterAccount.follower_count <= max_followers)
        
        stmt = (
            select(TwitterAccount)
            .where(and_(*conditions))
            .order_by(TwitterAccount.follower_count.desc())
            .limit(limit)
        )
        
        result = await self.db.execute(stmt)
        accounts = result.scalars().all()
        
        # 标记为已提取
        if mark_extracted and accounts:
            account_ids = [acc.id for acc in accounts]
            update_stmt = (
                update(TwitterAccount)
                .where(TwitterAccount.id.in_(account_ids))
                .values(is_extracted=True, extracted_at=datetime.utcnow())
            )
            await self.db.execute(update_stmt)
            await self.db.commit()
        
        return list(accounts)
    
    async def export_accounts(
        self,
        accounts: List[TwitterAccount],
        format: str = "text"
    ) -> str:
        """
        导出账号
        
        格式: 用户名----密码----2FA----邮箱----邮箱密码----粉丝数量----国家----年份----是否会员
        """
        if format == "text":
            lines = [account.to_export_format() for account in accounts]
            return "\n".join(lines)
        elif format == "json":
            import json
            return json.dumps([account.to_dict() for account in accounts], ensure_ascii=False, indent=2)
        else:
            raise ValueError(f"不支持的导出格式: {format}")
    
    # ==================== 统计信息 ====================
    
    async def get_status_statistics(self) -> Dict[str, int]:
        """获取状态统计 - 使用单条 GROUP BY 查询优化性能"""
        stmt = (
            select(
                TwitterAccount.status,
                func.count(TwitterAccount.id).label('count')
            )
            .group_by(TwitterAccount.status)
        )
        db_result = await self.db.execute(stmt)
        rows = db_result.all()
        
        # 初始化所有状态为 0
        result = {status.value: 0 for status in AccountStatus}
        # 填入实际统计值
        for row in rows:
            if row.status in result:
                result[row.status] = row.count
        
        return result
    
    async def get_overview_statistics(self) -> Dict[str, Any]:
        """获取总览统计 - 优化为单次聚合查询"""
        from sqlalchemy import case
        
        # 使用单条查询获取所有基础统计
        stmt = select(
            func.count(TwitterAccount.id).label('total'),
            func.sum(case(
                (TwitterAccount.status == AccountStatus.PENDING.value, 1),
                else_=0
            )).label('pending_count'),
            func.sum(case(
                (TwitterAccount.is_extracted == True, 1),
                else_=0
            )).label('extracted_count'),
            func.sum(case(
                (and_(
                    TwitterAccount.status == AccountStatus.NORMAL.value,
                    TwitterAccount.is_extracted == False
                ), 1),
                else_=0
            )).label('extractable_count'),
        ).select_from(TwitterAccount)
        
        result = await self.db.execute(stmt)
        row = result.one()
        
        total = row.total or 0
        pending_count = row.pending_count or 0
        extracted_count = row.extracted_count or 0
        extractable_count = row.extractable_count or 0
        checked_count = total - pending_count
        
        # 这些已经优化过，使用单次查询
        status_stats = await self.get_status_statistics()
        country_stats = await self.get_country_statistics()
        follower_stats = await self.get_follower_range_statistics()
        
        return {
            "total": total,
            "pending_count": pending_count,
            "checked_count": checked_count,
            "extracted_count": extracted_count,
            "extractable_count": extractable_count,
            "by_status": status_stats,
            "by_country": country_stats[:10],  # 前10个国家
            "by_follower_range": follower_stats
        }

