"""
数据库模型
"""
import re
from datetime import datetime
from typing import Optional
from enum import Enum

from sqlalchemy import String, Integer, Boolean, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AccountStatus(str, Enum):
    """账号状态枚举"""
    NORMAL = "正常"      # 正常可用
    SUSPENDED = "冻结"   # 已被冻结
    RESET_PWD = "改密"   # 需要改密
    NOT_FOUND = "不存在" # 账号不存在
    PENDING = "待检测"   # 待检测
    ERROR = "错误"       # 检测错误


class TwitterAccount(Base):
    """Twitter 账号模型"""
    __tablename__ = "twitter_accounts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 基础账号信息
    username: Mapped[str] = mapped_column(String(100), index=True)
    password: Mapped[str] = mapped_column(String(255))
    two_fa: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Token信息
    cookie: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auth_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # 账号属性
    follower_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    following_count: Mapped[int] = mapped_column(Integer, default=0)
    country: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    create_year: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # 状态信息
    status: Mapped[str] = mapped_column(
        String(20), 
        default=AccountStatus.PENDING.value,
        index=True
    )
    status_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 提取状态
    is_extracted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    extracted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # 原始数据
    raw_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 创建复合索引
    __table_args__ = (
        Index('idx_country_follower', 'country', 'follower_count'),
        Index('idx_status_country', 'status', 'country'),
        # 用于可提取账号查询优化 (status='正常' AND is_extracted=False)
        Index('idx_status_extracted', 'status', 'is_extracted'),
        # 用于粉丝范围查询优化
        Index('idx_status_follower', 'status', 'follower_count'),
    )
    
    def to_dict(self) -> dict:
        """转换为字典"""
        # 从 cookie 中提取 ct0 和 auth_token
        ct0 = ""
        auth_token = self.auth_token or ""
        if self.cookie:
            ct0_match = re.search(r'ct0=([^;]+)', self.cookie)
            if ct0_match:
                ct0 = f"ct0={ct0_match.group(1)}"
            # 如果 auth_token 字段为空，尝试从 cookie 中提取
            if not auth_token:
                auth_match = re.search(r'auth_token=([^;]+)', self.cookie)
                if auth_match:
                    auth_token = auth_match.group(1)
        
        return {
            "id": self.id,
            "username": self.username,
            "password": self.password,
            "two_fa": self.two_fa,
            "ct0": ct0,
            "auth_token": auth_token,
            "email": self.email,
            "email_password": self.email_password,
            "follower_count": self.follower_count,
            "following_count": self.following_count,
            "country": self.country,
            "create_year": self.create_year,
            "is_premium": self.is_premium,
            "status": self.status,
            "status_message": self.status_message,
            "is_extracted": self.is_extracted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
        }
    
    def to_export_format(self) -> str:
        """
        导出为指定格式:
        用户名----密码----2FA----ct0----authtoken----邮箱----邮箱密码----粉丝数量----国家----年份----是否会员
        """
        # 从 cookie 中提取 ct0 和 auth_token
        ct0 = ""
        auth_token = self.auth_token or ""
        if self.cookie:
            ct0_match = re.search(r'ct0=([^;]+)', self.cookie)
            if ct0_match:
                ct0 = f"ct0={ct0_match.group(1)}"
            # 如果 auth_token 字段为空，尝试从 cookie 中提取
            if not auth_token:
                auth_match = re.search(r'auth_token=([^;]+)', self.cookie)
                if auth_match:
                    auth_token = auth_match.group(1)
        
        premium_str = "会员" if self.is_premium else "普通用户"
        return (
            f"{self.username}----"
            f"{self.password}----"
            f"{self.two_fa or ''}----"
            f"{ct0}----"
            f"{auth_token}----"
            f"{self.email or ''}----"
            f"{self.email_password or ''}----"
            f"{self.follower_count}----"
            f"{self.country or ''}----"
            f"{self.create_year or ''}----"
            f"{premium_str}"
        )


class TaskConfig(Base):
    """任务配置模型 - 用于持久化任务状态"""
    __tablename__ = "task_config"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 任务配置
    proxy: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    concurrency: Mapped[int] = mapped_column(Integer, default=5)
    
    # 任务状态 (idle, running, paused, stopped, completed)
    status: Mapped[str] = mapped_column(String(20), default="idle")
    
    # 统计信息（运行时）
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    suspended_count: Mapped[int] = mapped_column(Integer, default=0)
    reset_pwd_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # 时间戳
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class CheckTask(Base):
    """检测任务模型"""
    __tablename__ = "check_tasks"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 任务信息
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    suspended_count: Mapped[int] = mapped_column(Integer, default=0)
    reset_pwd_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # 状态
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, running, completed, failed
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "total_count": self.total_count,
            "processed_count": self.processed_count,
            "success_count": self.success_count,
            "suspended_count": self.suspended_count,
            "reset_pwd_count": self.reset_pwd_count,
            "error_count": self.error_count,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

