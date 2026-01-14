"""
任务管理器 - 后台检测任务管理
"""
import asyncio
import random
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from dataclasses import dataclass, field
from collections import deque

from sqlalchemy import select, update, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models import TwitterAccount, TaskConfig
from twitter_client import TwitterClient
from tid_service import get_tid_service
import utils


class TaskStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"


@dataclass
class LogEntry:
    id: int
    time: str
    level: str
    message: str


@dataclass
class TaskState:
    status: TaskStatus = TaskStatus.IDLE
    total_count: int = 0
    pending_count: int = 0
    processed_count: int = 0
    success_count: int = 0
    suspended_count: int = 0
    reset_pwd_count: int = 0
    locked_count: int = 0
    error_count: int = 0
    started_at: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "total_count": self.total_count,
            "pending_count": self.pending_count,
            "processed_count": self.processed_count,
            "success_count": self.success_count,
            "suspended_count": self.suspended_count,
            "reset_pwd_count": self.reset_pwd_count,
            "locked_count": self.locked_count,
            "error_count": self.error_count,
            "started_at": self.started_at
        }


class TaskManager:
    """单例任务管理器"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.state = TaskState()
        self.logs: deque = deque(maxlen=1000)
        self.log_id_counter = 0
        self.proxy: Optional[str] = None
        self.concurrency: int = 5
        self._task: Optional[asyncio.Task] = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 默认不暂停
        self._stop_flag = False
        self._lock = asyncio.Lock()
    
    def add_log(self, level: str, message: str):
        """添加日志"""
        self.log_id_counter += 1
        # 使用北京时间 (UTC+8)
        from datetime import timezone, timedelta
        beijing_tz = timezone(timedelta(hours=8))
        now = datetime.now(beijing_tz)
        entry = LogEntry(
            id=self.log_id_counter,
            time=now.strftime("%H:%M:%S"),
            level=level,
            message=message
        )
        self.logs.append(entry)
    
    def get_logs(self, after_id: int = 0) -> List[dict]:
        """获取日志（支持增量获取）"""
        result = []
        for log in self.logs:
            if log.id > after_id:
                result.append({
                    "id": log.id,
                    "time": log.time,
                    "level": log.level,
                    "message": log.message
                })
        return result
    
    async def update_pending_count(self):
        """仅更新待检测数量（任务运行中使用）"""
        async with async_session() as db:
            stmt = select(func.count()).select_from(TwitterAccount).where(
                TwitterAccount.status == "待检测"
            )
            self.state.pending_count = (await db.execute(stmt)).scalar() or 0
    
    async def save_state_to_db(self):
        """保存任务状态到数据库"""
        async with async_session() as db:
            # 获取或创建配置记录（只保留一条）
            stmt = select(TaskConfig).where(TaskConfig.id == 1)
            result = await db.execute(stmt)
            config = result.scalar_one_or_none()
            
            if not config:
                config = TaskConfig(id=1)
                db.add(config)
            
            # 更新状态
            config.status = self.state.status.value
            config.proxy = self.proxy
            config.concurrency = self.concurrency
            config.processed_count = self.state.processed_count
            config.success_count = self.state.success_count
            config.suspended_count = self.state.suspended_count
            config.reset_pwd_count = self.state.reset_pwd_count
            config.locked_count = self.state.locked_count
            config.error_count = self.state.error_count
            config.started_at = datetime.fromisoformat(self.state.started_at) if self.state.started_at else None
            
            await db.commit()
    
    async def load_state_from_db(self):
        """从数据库加载任务状态"""
        async with async_session() as db:
            stmt = select(TaskConfig).where(TaskConfig.id == 1)
            result = await db.execute(stmt)
            config = result.scalar_one_or_none()
            
            if config:
                self.proxy = config.proxy
                self.concurrency = config.concurrency
                self.state.processed_count = config.processed_count
                self.state.success_count = config.success_count
                self.state.suspended_count = config.suspended_count
                self.state.reset_pwd_count = config.reset_pwd_count
                self.state.locked_count = getattr(config, 'locked_count', 0) or 0
                self.state.error_count = config.error_count
                self.state.started_at = config.started_at.isoformat() if config.started_at else None
                
                # 返回保存的状态
                return config.status
        return None
    
    async def get_config(self) -> dict:
        """获取任务配置"""
        async with async_session() as db:
            stmt = select(TaskConfig).where(TaskConfig.id == 1)
            result = await db.execute(stmt)
            config = result.scalar_one_or_none()
            
            if config:
                return {
                    "proxy": config.proxy or "",
                    "concurrency": config.concurrency or 5
                }
        return {"proxy": "", "concurrency": 5}
    
    async def save_config(self, proxy: str = None, concurrency: int = None) -> dict:
        """保存任务配置"""
        async with async_session() as db:
            stmt = select(TaskConfig).where(TaskConfig.id == 1)
            result = await db.execute(stmt)
            config = result.scalar_one_or_none()
            
            if not config:
                config = TaskConfig(id=1)
                db.add(config)
            
            if proxy is not None:
                config.proxy = proxy
                self.proxy = proxy
            if concurrency is not None:
                config.concurrency = concurrency
                self.concurrency = concurrency
            
            await db.commit()
            
            return {
                "proxy": config.proxy or "",
                "concurrency": config.concurrency or 5
            }
    
    async def restore_if_needed(self):
        """启动时检查是否需要恢复任务"""
        saved_status = await self.load_state_from_db()
        
        if saved_status in ['running', 'paused']:
            # 检查是否还有待检测的账号
            await self.update_counts_from_db()
            
            if self.state.pending_count > 0:
                self.add_log("info", f"检测到未完成的任务，正在恢复...")
                self.add_log("info", f"代理: {self.proxy or '无'}, 并发: {self.concurrency}")
                
                # 恢复运行
                self._stop_flag = False
                self._pause_event.set()
                self.state.status = TaskStatus.RUNNING
                
                # 启动 TID 服务（使用保存的代理）
                try:
                    tid_service = get_tid_service()
                    await tid_service.start(proxy=self.proxy)
                    self.add_log("info", "TID 服务启动中...")
                    
                    # 等待 TID 服务就绪
                    if await tid_service.wait_ready(timeout=30.0):
                        self.add_log("success", "TID 服务已就绪")
                    else:
                        self.add_log("warning", "TID 服务启动超时，将使用外部 TID 服务")
                except Exception as e:
                    self.add_log("warning", f"TID 服务启动失败: {str(e)[:100]}")
                
                # 启动后台任务
                self._task = asyncio.create_task(self._run_task())
                
                self.add_log("success", "任务已自动恢复运行")
                return True
            else:
                # 没有待检测的了，标记完成
                self.state.status = TaskStatus.COMPLETED
                await self.save_state_to_db()
                self.add_log("info", "任务已完成，无需恢复")
        
        return False
    
    async def update_counts_from_db(self):
        """从数据库更新所有统计数量 - 使用单次 GROUP BY 查询优化性能"""
        async with async_session() as db:
            # 使用单条查询获取所有统计
            stmt = select(
                func.count(TwitterAccount.id).label('total'),
                func.sum(case((TwitterAccount.status == "待检测", 1), else_=0)).label('pending'),
                func.sum(case((TwitterAccount.status == "正常", 1), else_=0)).label('success'),
                func.sum(case((TwitterAccount.status == "冻结", 1), else_=0)).label('suspended'),
                func.sum(case((TwitterAccount.status == "改密", 1), else_=0)).label('reset'),
                func.sum(case((TwitterAccount.status == "锁号", 1), else_=0)).label('locked'),
                func.sum(case((TwitterAccount.status == "错误", 1), else_=0)).label('error'),
            ).select_from(TwitterAccount)
            
            result = await db.execute(stmt)
            row = result.one()
            
            self.state.total_count = row.total or 0
            self.state.pending_count = row.pending or 0
            
            db_success = row.success or 0
            db_suspended = row.suspended or 0
            db_reset = row.reset or 0
            db_locked = row.locked or 0
            db_error = row.error or 0
            
            # 如果任务不在运行中，使用数据库的统计值
            if self.state.status not in [TaskStatus.RUNNING, TaskStatus.PAUSED]:
                self.state.success_count = db_success
                self.state.suspended_count = db_suspended
                self.state.reset_pwd_count = db_reset
                self.state.locked_count = db_locked
                self.state.error_count = db_error
                self.state.processed_count = self.state.total_count - self.state.pending_count
    
    async def start(self, proxy: Optional[str] = None, concurrency: int = 5):
        """启动任务"""
        async with self._lock:
            if self.state.status == TaskStatus.RUNNING:
                return {"success": False, "message": "任务已在运行中"}
            
            self.proxy = utils.parse_proxy(proxy) if proxy else None
            self.concurrency = min(max(concurrency, 1), 20)
            self._stop_flag = False
            self._pause_event.set()
            
            # 清空之前的日志
            self.logs.clear()
            self.log_id_counter = 0
            
            # 更新状态
            await self.update_counts_from_db()
            self.state.status = TaskStatus.RUNNING
            self.state.processed_count = 0
            self.state.success_count = 0
            self.state.suspended_count = 0
            self.state.reset_pwd_count = 0
            self.state.locked_count = 0
            self.state.error_count = 0
            self.state.started_at = datetime.now().isoformat()
            
            self.add_log("info", f"任务启动，代理: {self.proxy or '无'}, 并发: {self.concurrency}")
            
            # 启动 TID 服务（使用相同的代理）
            try:
                tid_service = get_tid_service()
                await tid_service.start(proxy=self.proxy)
                self.add_log("info", "TID 服务启动中...")
                
                # 等待 TID 服务就绪（最多等待30秒）
                if await tid_service.wait_ready(timeout=30.0):
                    self.add_log("success", "TID 服务已就绪")
                else:
                    self.add_log("warning", "TID 服务启动超时，将使用外部 TID 服务")
            except Exception as e:
                self.add_log("warning", f"TID 服务启动失败: {str(e)[:100]}，将使用外部 TID 服务")
            
            # 保存状态到数据库
            await self.save_state_to_db()
            
            # 启动后台任务
            self._task = asyncio.create_task(self._run_task())
            
            return {"success": True, "message": "任务已启动"}
    
    async def pause(self):
        """暂停任务"""
        if self.state.status != TaskStatus.RUNNING:
            return {"success": False, "message": "任务未在运行"}
        
        self._pause_event.clear()
        self.state.status = TaskStatus.PAUSED
        self.add_log("warning", "任务已暂停")
        await self.save_state_to_db()
        return {"success": True, "message": "任务已暂停"}
    
    async def resume(self):
        """恢复任务"""
        if self.state.status != TaskStatus.PAUSED:
            return {"success": False, "message": "任务未暂停"}
        
        self._pause_event.set()
        self.state.status = TaskStatus.RUNNING
        self.add_log("info", "任务已恢复")
        await self.save_state_to_db()
        return {"success": True, "message": "任务已恢复"}
    
    async def stop(self):
        """停止任务"""
        if self.state.status not in [TaskStatus.RUNNING, TaskStatus.PAUSED]:
            return {"success": False, "message": "任务未在运行"}
        
        self._stop_flag = True
        self._pause_event.set()  # 确保不会卡在暂停状态
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        # 停止 TID 服务
        try:
            tid_service = get_tid_service()
            await tid_service.stop()
            self.add_log("info", "TID 服务已停止")
        except Exception as e:
            self.add_log("warning", f"停止 TID 服务时出错: {str(e)[:50]}")
        
        self.state.status = TaskStatus.STOPPED
        self.add_log("error", "任务已停止")
        await self.save_state_to_db()
        return {"success": True, "message": "任务已停止"}
    
    async def get_status(self) -> dict:
        """获取任务状态"""
        await self.update_counts_from_db()
        return {"success": True, "data": self.state.to_dict()}
    
    async def clear_stats(self):
        """清空任务统计（仅清空面板统计，不删除账号数据）"""
        if self.state.status == TaskStatus.RUNNING:
            return {"success": False, "message": "任务运行中，无法清空统计"}
        
        # 清空面板统计
        self.state.processed_count = 0
        self.state.success_count = 0
        self.state.suspended_count = 0
        self.state.reset_pwd_count = 0
        self.state.locked_count = 0
        self.state.error_count = 0
        self.state.status = TaskStatus.IDLE
        self.state.started_at = None
        
        # 清空日志
        self.logs.clear()
        self.log_id_counter = 0
        
        # 保存到数据库
        await self.save_state_to_db()
        
        self.add_log("info", "任务统计已清空")
        return {"success": True, "message": "任务统计已清空"}
    
    async def _run_task(self):
        """后台执行检测任务 - 真正的并发执行"""
        try:
            while not self._stop_flag:
                # 检查暂停
                await self._pause_event.wait()
                
                if self._stop_flag:
                    break
                
                # 获取待检测账号
                async with async_session() as db:
                    stmt = select(TwitterAccount).where(
                        TwitterAccount.status == "待检测"
                    ).limit(self.concurrency)
                    result = await db.execute(stmt)
                    accounts = result.scalars().all()
                    
                    if not accounts:
                        self.state.status = TaskStatus.COMPLETED
                        self.add_log("success", "所有账号检测完成")
                        
                        # 停止 TID 服务
                        try:
                            tid_service = get_tid_service()
                            await tid_service.stop()
                            self.add_log("info", "TID 服务已停止")
                        except Exception as e:
                            pass
                        
                        await self.save_state_to_db()
                        # 检测完成后清零任务面板统计（数据库中的账号数据保持不变）
                        await self._reset_panel_stats()
                        break
                    
                    # 提取账号数据（避免 session 关闭后无法访问）
                    account_data_list = [
                        {
                            "id": acc.id,
                            "username": acc.username,
                            "password": acc.password,
                            "cookie": acc.cookie,
                            "email": acc.email,
                        }
                        for acc in accounts
                    ]
                
                # 并发检测 - 使用 asyncio.gather 实现真正的并发
                self.add_log("info", f"开始并发检测 {len(account_data_list)} 个账号...")
                
                tasks = [
                    self._check_account_concurrent(acc_data)
                    for acc_data in account_data_list
                ]
                
                # 并发执行所有检测任务
                await asyncio.gather(*tasks, return_exceptions=True)
                
                # 更新统计
                await self.update_pending_count()
                
                # 批次之间休息 0.5-1 秒
                await asyncio.sleep(random.uniform(0.5, 1.0))
        
        except asyncio.CancelledError:
            self.add_log("warning", "任务被取消")
        except Exception as e:
            self.add_log("error", f"任务异常: {str(e)}")
            self.state.status = TaskStatus.STOPPED
    
    async def _check_account_concurrent(self, acc_data: dict):
        """
        并发检测单个账号（使用独立的数据库 session）
        
        检测流程:
        1. Token登录获取完整信息 (accountData逻辑)，同时检测冻结状态
        2. Token登录失败 -> 找回密码检查邮箱
        3. 邮箱不匹配 -> 标记改密
        """
        # 检查暂停和停止
        await self._pause_event.wait()
        if self._stop_flag:
            return
        
        # 添加随机延迟，避免所有请求同时发出
        await asyncio.sleep(random.uniform(0.1, 0.5))
        
        account_id = acc_data["id"]
        username = acc_data["username"]
        password = acc_data["password"]
        cookie = acc_data.get("cookie")
        email = acc_data.get("email")
        
        try:
            # 🔍 开始检测
            self.add_log("info", f"🔍 开始检测: @{username}")
       
            # 创建客户端
            client = TwitterClient(
                cookie=cookie or "",
                proxy=self.proxy,
                password=password
            )
            client.username = username
            
            # 使用独立的 session 更新数据库
            async with async_session() as db:
                # 重新获取账号对象
                stmt = select(TwitterAccount).where(TwitterAccount.id == account_id)
                result = await db.execute(stmt)
                account = result.scalar_one_or_none()
                
                if not account:
                    self.add_log("error", f"@{username} - 账号记录不存在")
                    return
                
                # ========== 步骤1: Token登录获取完整信息（同时检测冻结） ==========
                if cookie:
                    self.add_log("info", f"📋 @{username} 步骤1: Token登录获取完整信息...")
                    try:
                        account_info = await client.account_data(password)
                        
                        # 更新账号信息
                        account.follower_count = client.follower_count
                        account.following_count = client.following_count
                        account.country = client.country
                        account.is_premium = client.is_premium
                        
                        # 解析创建年份
                        if client.create_time:
                            parts = client.create_time.split()
                            account.create_year = parts[-1] if parts else ""
                        
                        # 更新cookie
                        account.cookie = client.cookie
                        
                        account.status = "正常"
                        account.status_message = "正常"
                        self.state.success_count += 1
                        
                        premium_str = "会员" if account.is_premium else "普通用户"
                        self.add_log("success", f"✓ @{username} 步骤1结果: Token登录成功")
                        self.add_log("success", 
                            f"✅ @{username} 检测完成: 正常 | 粉丝:{account.follower_count} | "
                            f"关注:{account.following_count} | 国家:{account.country or '未知'} | "
                            f"年份:{account.create_year or '未知'} | {premium_str}")
                        
                        account.checked_at = datetime.utcnow()
                        self.state.processed_count += 1
                        await db.commit()
                        return
                        
                    except Exception as e:
                        error_msg = str(e).lower()
                        original_error = str(e)
                        self.add_log("warning", f"⚠️ @{username} 步骤1结果: Token登录失败 - {original_error[:100]}")
                        
                        # 检测是否冻结 (suspended)
                        is_suspended = (
                            "suspend" in error_msg or
                            "冻结" in error_msg or
                            "userunavailable" in error_msg
                        )
                        
                        if is_suspended:
                            account.status = "冻结"
                            account.status_message = "账号已冻结"
                            self.state.suspended_count += 1
                            self.add_log("error", f"❌ @{username} 检测完成: 账号已冻结")
                            account.checked_at = datetime.utcnow()
                            self.state.processed_count += 1
                            await db.commit()
                            return
                        
                        # 检测账号是否不存在
                        is_not_exist = (
                            "不存在" in error_msg or
                            "not found" in error_msg or
                            "user not found" in error_msg
                        )
                        
                        if is_not_exist:
                            account.status = "错误"
                            account.status_message = "账号不存在"
                            self.state.error_count += 1
                            self.add_log("error", f"❌ @{username} 检测完成: 账号不存在")
                            account.checked_at = datetime.utcnow()
                            self.state.processed_count += 1
                            await db.commit()
                            return
                        
                        # 检测是否token失效 (code 32 = Could not authenticate you)
                        # Token失效需要走邮箱逻辑，不能直接标记锁号
                        is_token_expired = (
                            "could not authenticate" in error_msg or
                            "code\":32" in error_msg or
                            '"code":32' in error_msg or
                            "code: 32" in error_msg
                        )
                        
                        if is_token_expired:
                            self.add_log("warning", f"⚠️ @{username} Token已失效，继续检查找回密码邮箱...")
                            # Token失效，继续步骤2检查邮箱
                        else:
                            # 如果是密码验证错误（非token失效），标记锁号
                            is_locked = (
                                "密码" in error_msg or 
                                "password" in error_msg or 
                                "verify" in error_msg or 
                                "验证" in error_msg
                            )
                            
                            if is_locked:
                                account.status = "锁号"
                                account.status_message = f"密码验证失败: {original_error[:100]}"
                                self.state.locked_count += 1
                                self.add_log("warning", f"⚠️ @{username} 检测完成: 锁号(密码验证失败)")
                                account.checked_at = datetime.utcnow()
                                self.state.processed_count += 1
                                await db.commit()
                                return
                        
                        # Token失效或其他错误，继续步骤2检查找回密码邮箱
                else:
                    self.add_log("warning", f"⚠️ @{username} 步骤1: 无Cookie，跳过Token登录")
                
                # ========== 步骤2: 检查找回密码邮箱 ==========
                self.add_log("info", f"📋 @{username} 步骤2: 检查找回密码邮箱...")
                await self._check_password_reset_email_with_steps(account, client, email)
                
                account.checked_at = datetime.utcnow()
                self.state.processed_count += 1
                await db.commit()
                
        except Exception as e:
            # 使用独立 session 更新错误状态
            async with async_session() as db:
                stmt = select(TwitterAccount).where(TwitterAccount.id == account_id)
                result = await db.execute(stmt)
                account = result.scalar_one_or_none()
                if account:
                    account.status = "错误"
                    account.status_message = str(e)[:200]
                    account.checked_at = datetime.utcnow()
                    await db.commit()
            
            self.state.error_count += 1
            self.state.processed_count += 1
            self.add_log("error", f"❌ @{username} - 检测异常: {str(e)[:200]}")
    
    async def _check_account(self, db: AsyncSession, account: TwitterAccount):
        """
        检测单个账号
        
        流程:
        1. Token登录获取完整信息 (accountData逻辑)，同时检测冻结状态
        2. Token登录失败 -> 找回密码检查邮箱
        3. 邮箱不匹配 -> 标记改密
        
        返回格式: 用户名----密码----2FA----邮箱----邮箱密码----粉丝数量----国家----年份----是否会员
        """
        username = account.username
        password = account.password
        
        try:
            self.add_log("info", f"开始检测: @{username}")
            
            # 创建客户端
            client = TwitterClient(
                cookie=account.cookie or "",
                proxy=self.proxy,
                password=password
            )
            client.username = username
            
            # 1. 使用Token登录获取完整信息（同时检测冻结状态）
            if account.cookie:
                try:
                    # 使用 accountData 逻辑获取完整信息
                    self.add_log("info", f"@{username} - Token登录获取信息...")
                    account_info = await client.account_data(password)
                    
                    # 更新账号信息
                    account.follower_count = client.follower_count
                    account.following_count = client.following_count
                    account.country = client.country
                    account.is_premium = client.is_premium
                    
                    # 解析创建年份
                    if client.create_time:
                        parts = client.create_time.split()
                        account.create_year = parts[-1] if parts else ""
                    
                    # 更新cookie
                    account.cookie = client.cookie
                    
                    account.status = "正常"
                    account.status_message = "正常"
                    self.state.success_count += 1
                    
                    # 生成导出格式日志
                    premium_str = "会员" if account.is_premium else "普通用户"
                    self.add_log("success", 
                        f"@{username} - 正常 | 粉丝:{account.follower_count} | "
                        f"国家:{account.country or '未知'} | 年份:{account.create_year or '未知'} | {premium_str}")
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    original_error = str(e)
                    self.add_log("warning", f"@{username} - Token登录失败: {original_error[:200]}")
                    
                    # 检测是否冻结 (suspended)
                    is_suspended = (
                        "suspend" in error_msg or
                        "冻结" in error_msg or
                        "userunavailable" in error_msg
                    )
                    
                    if is_suspended:
                        account.status = "冻结"
                        account.status_message = "账号已冻结"
                        self.state.suspended_count += 1
                        self.add_log("error", f"@{username} - 冻结")
                        account.checked_at = datetime.utcnow()
                        self.state.processed_count += 1
                        return
                    
                    # 检测账号是否不存在
                    is_not_exist = (
                        "不存在" in error_msg or
                        "not found" in error_msg or
                        "user not found" in error_msg
                    )
                    
                    if is_not_exist:
                        account.status = "错误"
                        account.status_message = "账号不存在"
                        self.state.error_count += 1
                        self.add_log("error", f"@{username} - 账号不存在")
                        account.checked_at = datetime.utcnow()
                        self.state.processed_count += 1
                        return
                    
                    # 检测是否token失效 (code 32 = Could not authenticate you)
                    # Token失效需要走邮箱逻辑，不能直接标记锁号
                    is_token_expired = (
                        "could not authenticate" in error_msg or
                        "code\":32" in error_msg or
                        '"code":32' in error_msg or
                        "code: 32" in error_msg
                    )
                    
                    if is_token_expired:
                        self.add_log("warning", f"@{username} - Token已失效，检查找回密码邮箱...")
                        await self._check_password_reset_email(account, client)
                    else:
                        # 如果是密码验证错误（非token失效），标记锁号
                        is_locked = (
                            "密码" in error_msg or 
                            "password" in error_msg or 
                            "verify" in error_msg or 
                            "验证" in error_msg
                        )
                        
                        if is_locked:
                            account.status = "锁号"
                            account.status_message = f"密码验证失败: {original_error[:100]}"
                            self.state.locked_count += 1
                            self.add_log("warning", f"@{username} - 锁号(密码验证失败)")
                        else:
                            # 其他错误，检查找回密码邮箱
                            await self._check_password_reset_email(account, client)
            else:
                # 没有cookie，尝试检查找回密码邮箱
                self.add_log("info", f"@{username} - 无Cookie，检查找回密码邮箱...")
                await self._check_password_reset_email(account, client)
            
            account.checked_at = datetime.utcnow()
            self.state.processed_count += 1
            
        except Exception as e:
            account.status = "错误"
            account.status_message = str(e)[:200]
            self.state.error_count += 1
            self.state.processed_count += 1
            self.add_log("error", f"@{username} - 错误: {str(e)[:200]}")
    
    async def _reset_panel_stats(self):
        """任务完成后重置面板统计（不影响数据库中的账号数据）"""
        self.state.processed_count = 0
        self.state.success_count = 0
        self.state.suspended_count = 0
        self.state.reset_pwd_count = 0
        self.state.locked_count = 0
        self.state.error_count = 0
        self.add_log("info", "任务面板已清零")
    
    async def _check_password_reset_email_with_steps(self, account: TwitterAccount, client: TwitterClient, expected_email: str = None):
        """
        检查找回密码邮箱（带详细步骤日志）
        
        例: q2c716@tuitegmail.com 发送到 q2****@t*********.***
        如果不匹配则标记为"改密"
        """
        username = account.username
        expected_email = expected_email or account.email
        
        try:
            # 获取找回密码显示的脱敏邮箱 (带重试机制)
            email_result = await client.get_password_reset_email_hint(username)
            masked_email = email_result.get("email_hint") if email_result.get("success") else None
            
            # 显示重试信息
            if email_result.get("retry_count", 0) > 0:
                self.add_log("info", f"   @{username} (重试了 {email_result.get('retry_count')} 次)")
            
            if not masked_email:
                # 打印完整响应，方便调试
                self.add_log("info", f"📦 @{username} get_password_reset_email_hint 完整响应:")
                self.add_log("info", f"   success: {email_result.get('success')}")
                self.add_log("info", f"   email_hint: {email_result.get('email_hint')}")
                self.add_log("info", f"   error: {email_result.get('error')}")
                self.add_log("info", f"   retry_count: {email_result.get('retry_count', 0)}")
                self.add_log("info", f"   is_network_error: {email_result.get('is_network_error', False)}")
                
                # 区分网络错误和其他错误
                if email_result.get("is_network_error") or "重试" in str(email_result.get("error", "")):
                    account.status = "错误"
                    account.status_message = f"网络错误: {email_result.get('error', '未知')[:100]}"
                    self.state.error_count += 1
                    self.add_log("error", f"⚠️ @{username} 步骤2结果: 网络错误 - {email_result.get('error', '')[:100]}")
                else:
                    account.status = "改密"
                    account.status_message = email_result.get("error") or "无法获取找回密码邮箱提示"
                    self.state.reset_pwd_count += 1
                    self.add_log("warning", f"⚠️ @{username} 步骤2结果: 无法获取找回邮箱 - {email_result.get('error', '')[:150]}")
                    self.add_log("warning", f"⚠️ @{username} 检测完成: 改密")
                return
            
            self.add_log("info", f"   @{username} 找回密码显示邮箱: {masked_email}")
            
            if expected_email:
                self.add_log("info", f"   @{username} 期望邮箱: {expected_email}")
                
                # 比较邮箱是否匹配
                if utils.compare_masked_email(expected_email, masked_email):
                    # 邮箱匹配，但Token登录失败，需要改密
                    self.add_log("success", f"   ✓ @{username} 邮箱匹配!")
                    account.status = "改密"
                    account.status_message = f"邮箱匹配({masked_email})，但登录失败需改密"
                    self.state.reset_pwd_count += 1
                    self.add_log("warning", f"⚠️ @{username} 检测完成: 改密(邮箱匹配但登录失败)")
                else:
                    # 邮箱不匹配，标记改密
                    self.add_log("error", f"   ✗ @{username} 邮箱不匹配!")
                    account.status = "改密"
                    account.status_message = f"邮箱不匹配！期望:{expected_email}, 实际:{masked_email}"
                    self.state.reset_pwd_count += 1
                    self.add_log("error", f"❌ @{username} 检测完成: 改密(邮箱不匹配)")
            else:
                # 没有提供期望邮箱，直接标记为改密
                account.status = "改密"
                account.status_message = f"找回密码邮箱: {masked_email}"
                self.state.reset_pwd_count += 1
                self.add_log("warning", f"⚠️ @{username} 检测完成: 改密(找回邮箱:{masked_email})")
                
        except Exception as e:
            account.status = "错误"
            account.status_message = f"检查找回密码失败: {str(e)[:100]}"
            self.state.error_count += 1
            self.add_log("error", f"❌ @{username} 步骤2异常: {str(e)[:100]}")

    async def _check_password_reset_email(self, account: TwitterAccount, client: TwitterClient):
        """
        检查找回密码邮箱是否与账号绑定邮箱匹配（兼容旧调用）
        
        例: q2c716@tuitegmail.com 发送到 q2****@t*********.***
        如果不匹配则标记为"改密"
        """
        await self._check_password_reset_email_with_steps(account, client, account.email)


# 全局任务管理器实例
task_manager = TaskManager()

