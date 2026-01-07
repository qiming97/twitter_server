"""
API 请求/响应模型
"""
from typing import Optional, List, Any
from pydantic import BaseModel, Field


# ==================== 请求模型 ====================

class AccountCheckRequest(BaseModel):
    """单个账号检测请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    two_fa: Optional[str] = Field(None, description="2FA密钥")
    email: Optional[str] = Field(None, description="邮箱")
    email_password: Optional[str] = Field(None, description="邮箱密码")
    cookie: Optional[str] = Field(None, description="Cookie")
    proxy: Optional[str] = Field(None, description="代理")


class BatchCheckRequest(BaseModel):
    """批量检测请求"""
    accounts: List[AccountCheckRequest] = Field(..., description="账号列表")
    proxy: Optional[str] = Field(None, description="代理")
    concurrency: int = Field(5, description="并发数", ge=1, le=20)


class ExtractAccountsRequest(BaseModel):
    """提取账号请求"""
    country: Optional[str] = Field(None, description="国家筛选")
    min_followers: int = Field(0, description="最小粉丝数")
    max_followers: int = Field(999999999, description="最大粉丝数")
    limit: int = Field(100, description="提取数量", ge=1, le=10000)
    status: str = Field("正常", description="账号状态")


class ImportAccountsRequest(BaseModel):
    """导入账号请求（文本格式）"""
    accounts_text: str = Field(..., description="账号文本，每行一个")
    delimiter: str = Field("----", description="分隔符")
    proxy: Optional[str] = Field(None, description="代理")
    auto_check: bool = Field(False, description="是否自动检测")


class AccountDataItem(BaseModel):
    """单个账号数据"""
    username: str
    password: str = ""
    two_fa: Optional[str] = None
    cookie: Optional[str] = None
    auth_token: Optional[str] = None
    email: Optional[str] = None
    email_password: Optional[str] = None
    follower_count: int = 0
    country: Optional[str] = None
    create_year: Optional[str] = None
    is_premium: bool = False


class ImportAccountsDataRequest(BaseModel):
    """导入账号请求（JSON 数据格式，支持 Excel 解析后的数据）"""
    accounts: List[AccountDataItem] = Field(..., description="账号数据列表")
    proxy: Optional[str] = Field(None, description="代理")
    auto_check: bool = Field(False, description="是否自动检测")


# ==================== 响应模型 ====================

class AccountResponse(BaseModel):
    """账号响应"""
    id: int
    username: str
    password: str
    two_fa: Optional[str] = None
    email: Optional[str] = None
    email_password: Optional[str] = None
    follower_count: int = 0
    following_count: int = 0
    country: Optional[str] = None
    create_year: Optional[str] = None
    is_premium: bool = False
    status: str
    status_message: Optional[str] = None
    created_at: Optional[str] = None
    checked_at: Optional[str] = None


class CheckTaskResponse(BaseModel):
    """检测任务响应"""
    id: int
    total_count: int
    processed_count: int
    success_count: int
    suspended_count: int
    reset_pwd_count: int
    error_count: int
    status: str
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class PaginatedResponse(BaseModel):
    """分页响应"""
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


class StatisticsResponse(BaseModel):
    """统计响应"""
    total: int
    pending_count: int = 0
    checked_count: int = 0
    extracted_count: int = 0
    extractable_count: int = 0
    by_status: dict
    by_country: List[dict]
    by_follower_range: List[dict]


class CountryStatItem(BaseModel):
    """国家统计项"""
    country: str
    count: int


class FollowerRangeStatItem(BaseModel):
    """粉丝范围统计项"""
    range: str
    min: int
    max: int
    count: int


class ApiResponse(BaseModel):
    """通用API响应"""
    success: bool = True
    message: str = "success"
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = False
    message: str
    error_code: Optional[str] = None

