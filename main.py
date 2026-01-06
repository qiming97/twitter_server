"""
Twitter Server - FastAPI 主入口
提供账号检测、分类、提取等 API 服务
"""
import math
import os
from contextlib import asynccontextmanager
from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import init_db, get_db
from models import AccountStatus, TwitterAccount
from services import AccountService
from schemas import (
    AccountCheckRequest,
    BatchCheckRequest,
    ExtractAccountsRequest,
    ImportAccountsRequest,
    ImportAccountsDataRequest,
    AccountResponse,
    CheckTaskResponse,
    PaginatedResponse,
    StatisticsResponse,
    ApiResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    await init_db()
    print("✓ 数据库初始化完成")
    
    # 检查是否需要恢复之前的任务
    restored = await task_manager.restore_if_needed()
    if restored:
        print("✓ 检测任务已自动恢复")
    else:
        print("✓ 无需恢复任务")
    
    yield
    # 关闭时清理资源
    print("✓ 服务关闭")


app = FastAPI(
    title="Twitter Server",
    description="""
    Twitter 账号检测服务
    
    功能:
    - 检测账号冻结状态
    - Token登录获取账号信息
    - 找回密码邮箱匹配检测
    - 账号分类（按国家/粉丝数量）
    - 账号提取
    """,
    version="1.0.0",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件目录
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ==================== 账号检测 API ====================

@app.post("/api/check/single", response_model=ApiResponse, tags=["检测"])
async def check_single_account(
    request: AccountCheckRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    检测单个账号
    
    流程:
    1. x.com/用户名 查询是否冻结
    2. 未冻结则使用Token登陆获取粉丝数量等信息
    3. Token登陆失败则检查找回密码邮箱是否匹配
    """
    service = AccountService(db)
    
    try:
        account = await service.check_single_account(
            username=request.username,
            password=request.password,
            two_fa=request.two_fa,
            email=request.email,
            email_password=request.email_password,
            cookie=request.cookie,
            proxy=request.proxy
        )
        
        return ApiResponse(
            success=True,
            message="检测完成",
            data=account.to_dict()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/check/batch", response_model=ApiResponse, tags=["检测"])
async def check_batch_accounts(
    request: BatchCheckRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    批量检测账号
    
    会在后台执行检测任务，返回任务ID
    """
    service = AccountService(db)
    
    try:
        accounts_data = [
            {
                "username": acc.username,
                "password": acc.password,
                "two_fa": acc.two_fa,
                "email": acc.email,
                "email_password": acc.email_password,
                "cookie": acc.cookie,
            }
            for acc in request.accounts
        ]
        
        task = await service.batch_check_accounts(
            accounts_data=accounts_data,
            proxy=request.proxy,
            concurrency=request.concurrency
        )
        
        return ApiResponse(
            success=True,
            message="批量检测完成",
            data=task.to_dict()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/import", response_model=ApiResponse, tags=["导入"])
async def import_accounts(
    request: ImportAccountsRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    导入账号
    
    支持格式: 用户名----密码----2FA----邮箱----邮箱密码
    """
    service = AccountService(db)
    
    try:
        lines = request.accounts_text.strip().split("\n")
        accounts_data = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split(request.delimiter)
            if len(parts) >= 2:
                account_data = {
                    "username": parts[0].strip(),
                    "password": parts[1].strip(),
                }
                if len(parts) >= 3:
                    account_data["two_fa"] = parts[2].strip() or None
                if len(parts) >= 4:
                    account_data["email"] = parts[3].strip() or None
                if len(parts) >= 5:
                    account_data["email_password"] = parts[4].strip() or None
                if len(parts) >= 6:
                    account_data["cookie"] = parts[5].strip() or None
                
                accounts_data.append(account_data)
        
        if request.auto_check:
            # 自动检测
            task = await service.batch_check_accounts(
                accounts_data=accounts_data,
                proxy=request.proxy,
                concurrency=5
            )
            return ApiResponse(
                success=True,
                message=f"导入并检测完成，共 {len(accounts_data)} 个账号",
                data=task.to_dict()
            )
        else:
            # 仅导入不检测
            for data in accounts_data:
                await service._get_or_create_account(
                    data["username"],
                    data["password"]
                )
            await db.commit()
            
            return ApiResponse(
                success=True,
                message=f"导入完成，共 {len(accounts_data)} 个账号",
                data={"count": len(accounts_data)}
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/import/data", response_model=ApiResponse, tags=["导入"])
async def import_accounts_data(
    request: ImportAccountsDataRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    导入账号（JSON 数据格式）
    
    支持从 Excel 解析后的数据导入，包含完整的账号信息
    """
    service = AccountService(db)
    
    try:
        accounts_data = []
        
        for acc in request.accounts:
            account_data = {
                "username": acc.username,
                "password": acc.password,
                "two_fa": acc.two_fa,
                "cookie": acc.cookie,
                "email": acc.email,
                "email_password": acc.email_password,
                "follower_count": acc.follower_count,
                "country": acc.country,
                "create_year": acc.create_year,
                "is_premium": acc.is_premium,
            }
            accounts_data.append(account_data)
        
        if request.auto_check:
            # 自动检测
            task = await service.batch_check_accounts(
                accounts_data=accounts_data,
                proxy=request.proxy,
                concurrency=5
            )
            return ApiResponse(
                success=True,
                message=f"导入并检测完成，共 {len(accounts_data)} 个账号",
                data=task.to_dict()
            )
        else:
            # 仅导入不检测（包含完整数据）
            for data in accounts_data:
                account = await service._get_or_create_account(
                    data["username"],
                    data["password"]
                )
                # 更新额外信息
                if data.get("two_fa"):
                    account.two_fa = data["two_fa"]
                if data.get("cookie"):
                    account.cookie = data["cookie"]
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
            
            await db.commit()
            
            return ApiResponse(
                success=True,
                message=f"导入完成，共 {len(accounts_data)} 个账号",
                data={
                    "count": len(accounts_data),
                    "total_count": len(accounts_data),
                    "processed_count": len(accounts_data),
                    "success_count": len(accounts_data),
                    "suspended_count": 0,
                    "reset_pwd_count": 0,
                    "status": "completed"
                }
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 账号分类 API ====================

@app.get("/api/accounts/status/{status}", response_model=PaginatedResponse, tags=["分类"])
async def get_accounts_by_status(
    status: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    is_extracted: Optional[bool] = Query(None, description="是否已提取"),
    db: AsyncSession = Depends(get_db)
):
    """按状态获取账号: 正常、冻结、改密"""
    service = AccountService(db)
    accounts, total = await service.get_accounts_by_status(
        status=status,
        page=page,
        page_size=page_size,
        is_extracted=is_extracted
    )
    
    return PaginatedResponse(
        items=[acc.to_dict() for acc in accounts],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size)
    )


@app.get("/api/accounts/country/{country}", response_model=PaginatedResponse, tags=["分类"])
async def get_accounts_by_country(
    country: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    is_extracted: Optional[bool] = Query(None, description="是否已提取"),
    db: AsyncSession = Depends(get_db)
):
    """按国家获取账号"""
    service = AccountService(db)
    accounts, total = await service.get_accounts_by_country(
        country=country,
        page=page,
        page_size=page_size,
        is_extracted=is_extracted
    )
    
    return PaginatedResponse(
        items=[acc.to_dict() for acc in accounts],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size)
    )


@app.get("/api/accounts/followers", response_model=PaginatedResponse, tags=["分类"])
async def get_accounts_by_follower_range(
    min_followers: int = Query(0, ge=0),
    max_followers: int = Query(999999999, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    is_extracted: Optional[bool] = Query(None, description="是否已提取"),
    db: AsyncSession = Depends(get_db)
):
    """按粉丝数量范围获取账号"""
    service = AccountService(db)
    accounts, total = await service.get_accounts_by_follower_range(
        min_followers=min_followers,
        max_followers=max_followers,
        page=page,
        page_size=page_size,
        is_extracted=is_extracted
    )
    
    return PaginatedResponse(
        items=[acc.to_dict() for acc in accounts],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size)
    )


# ==================== 账号提取 API ====================

@app.post("/api/extract", response_model=ApiResponse, tags=["提取"])
async def extract_accounts(
    request: ExtractAccountsRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    提取账号
    
    例: 日本，粉丝数量：0-9个，提取100个
    """
    service = AccountService(db)
    
    accounts = await service.extract_accounts(
        country=request.country,
        min_followers=request.min_followers,
        max_followers=request.max_followers,
        limit=request.limit,
        status=request.status
    )
    
    return ApiResponse(
        success=True,
        message=f"提取完成，共 {len(accounts)} 个账号",
        data=[acc.to_dict() for acc in accounts]
    )


@app.post("/api/extract/export", tags=["提取"])
async def export_accounts(
    request: ExtractAccountsRequest,
    format: str = Query("text", description="导出格式: text, json"),
    db: AsyncSession = Depends(get_db)
):
    """
    导出账号
    
    格式: 用户名----密码----2FA----邮箱----邮箱密码----粉丝数量----国家----年份----是否会员
    """
    service = AccountService(db)
    
    accounts = await service.extract_accounts(
        country=request.country,
        min_followers=request.min_followers,
        max_followers=request.max_followers,
        limit=request.limit,
        status=request.status
    )
    
    export_content = await service.export_accounts(accounts, format=format)
    
    if format == "text":
        return PlainTextResponse(
            content=export_content,
            media_type="text/plain",
            headers={
                "Content-Disposition": "attachment; filename=accounts.txt"
            }
        )
    else:
        return ApiResponse(
            success=True,
            message=f"导出完成，共 {len(accounts)} 个账号",
            data=export_content
        )


# ==================== 统计 API ====================

@app.get("/api/statistics", response_model=StatisticsResponse, tags=["统计"])
async def get_statistics(
    db: AsyncSession = Depends(get_db)
):
    """获取统计信息"""
    service = AccountService(db)
    stats = await service.get_overview_statistics()
    return stats


@app.get("/api/statistics/countries", response_model=ApiResponse, tags=["统计"])
async def get_country_statistics(
    db: AsyncSession = Depends(get_db)
):
    """获取国家统计"""
    service = AccountService(db)
    stats = await service.get_country_statistics()
    return ApiResponse(
        success=True,
        data=stats
    )


@app.get("/api/statistics/followers", response_model=ApiResponse, tags=["统计"])
async def get_follower_statistics(
    db: AsyncSession = Depends(get_db)
):
    """获取粉丝数量区间统计"""
    service = AccountService(db)
    stats = await service.get_follower_range_statistics()
    return ApiResponse(
        success=True,
        data=stats
    )


# ==================== 任务管理 API ====================

from task_manager import task_manager


class TaskStartRequest(BaseModel):
    proxy: Optional[str] = None
    concurrency: int = 5


@app.get("/api/task/status", response_model=ApiResponse, tags=["任务管理"])
async def get_task_status():
    """获取任务状态"""
    return await task_manager.get_status()


@app.get("/api/task/config", response_model=ApiResponse, tags=["任务管理"])
async def get_task_config():
    """获取任务配置"""
    config = await task_manager.get_config()
    return ApiResponse(success=True, data=config)


@app.post("/api/task/config", response_model=ApiResponse, tags=["任务管理"])
async def save_task_config(request: dict):
    """保存任务配置"""
    config = await task_manager.save_config(
        proxy=request.get("proxy"),
        concurrency=request.get("concurrency")
    )
    return ApiResponse(success=True, data=config, message="配置已保存")


@app.get("/api/task/logs", response_model=ApiResponse, tags=["任务管理"])
async def get_task_logs(after_id: int = Query(0, description="获取此ID之后的日志")):
    """获取任务日志（支持增量获取）"""
    logs = task_manager.get_logs(after_id)
    return ApiResponse(success=True, data=logs)


@app.post("/api/task/start", response_model=ApiResponse, tags=["任务管理"])
async def start_task(request: TaskStartRequest):
    """启动检测任务"""
    result = await task_manager.start(
        proxy=request.proxy,
        concurrency=request.concurrency
    )
    return ApiResponse(**result)


@app.post("/api/task/pause", response_model=ApiResponse, tags=["任务管理"])
async def pause_task():
    """暂停任务"""
    result = await task_manager.pause()
    return ApiResponse(**result)


@app.post("/api/task/resume", response_model=ApiResponse, tags=["任务管理"])
async def resume_task():
    """恢复任务"""
    result = await task_manager.resume()
    return ApiResponse(**result)


@app.post("/api/task/stop", response_model=ApiResponse, tags=["任务管理"])
async def stop_task():
    """停止任务"""
    result = await task_manager.stop()
    return ApiResponse(**result)


# ==================== 账号管理 ====================

@app.post("/api/accounts/reset-status", response_model=ApiResponse, tags=["账号管理"])
async def reset_all_accounts_status(db: AsyncSession = Depends(get_db)):
    """
    重置所有账号状态为待检测
    """
    from sqlalchemy import update
    
    try:
        stmt = update(TwitterAccount).values(
            status=AccountStatus.PENDING.value,
            status_message="待检测",
            checked_at=None
        )
        result = await db.execute(stmt)
        await db.commit()
        
        count = result.rowcount
        return ApiResponse(
            success=True,
            message=f"已将 {count} 个账号状态重置为待检测",
            data={"count": count}
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/accounts/clear", response_model=ApiResponse, tags=["账号管理"])
async def clear_all_accounts(db: AsyncSession = Depends(get_db)):
    """
    清空所有账号
    """
    from sqlalchemy import delete
    
    try:
        stmt = delete(TwitterAccount)
        result = await db.execute(stmt)
        await db.commit()
        
        count = result.rowcount
        return ApiResponse(
            success=True,
            message=f"已删除 {count} 个账号",
            data={"count": count}
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 健康检查 ====================

@app.get("/health", tags=["系统"])
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "twitter-server"}


@app.get("/", tags=["系统"])
async def root():
    """根路径 - 返回前端页面"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file), media_type="text/html")
    return {
        "service": "Twitter Server",
        "version": "1.0.0",
        "docs": "/docs"
    }


# History 模式路由支持 - 前端路由
FRONTEND_ROUTES = ["/dashboard", "/import", "/task", "/accounts", "/extract"]

@app.get("/{path:path}", tags=["系统"])
async def catch_all(path: str):
    """
    Catch-all 路由 - 支持 Vue Router history 模式
    前端路由都返回 index.html
    """
    # 检查是否是前端路由
    if f"/{path}" in FRONTEND_ROUTES or path in [r.lstrip('/') for r in FRONTEND_ROUTES]:
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file), media_type="text/html")
    
    # 检查是否是静态文件
    static_file = STATIC_DIR / path
    if static_file.exists() and static_file.is_file():
        return FileResponse(str(static_file))
    
    # 404
    raise HTTPException(status_code=404, detail="Not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )

