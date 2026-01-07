"""
配置文件
"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 数据库配置
    DATABASE_URL: str = "sqlite+aiosqlite:///./twitter_accounts.db"
    
    # 服务配置
    HOST: str = "0.0.0.0"
    PORT: int = 35901
    DEBUG: bool = True
    
    # Twitter API 相关
    TWITTER_BEARER_TOKEN: str = "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
    
    # TID 算法服务地址
    TID_SERVICE_URL: str = "http://167.160.190.214:7700/getTid"
    
    # 2FA 服务地址
    TWO_FA_SERVICE_URL: str = "https://2fa.live/tok/"
    
    class Config:
        env_file = ".env"


settings = Settings()

