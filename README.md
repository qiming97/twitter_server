# Twitter Server

Twitter 账号检测、分类、提取服务。

## 功能

1. **账号冻结检测**: 通过 `x.com/用户名` 查询账号是否被冻结
2. **Token登录验证**: 使用Cookie/Token登录获取粉丝数量、国家、年份等信息
3. **密码找回检测**: Token登录失败时，检查找回密码邮箱是否与提供的邮箱匹配
4. **账号分类**: 按状态（冻结/正常/改密）、国家、粉丝数量分类
5. **账号提取**: 按条件提取账号（国家、粉丝数量区间、数量限制）

## 安装

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

## 配置

创建 `.env` 文件或直接修改 `config.py`:

```env
DATABASE_URL=sqlite+aiosqlite:///./twitter_accounts.db
HOST=0.0.0.0
PORT=8000
DEBUG=true
TID_SERVICE_URL=http://localhost:7700/gettid
```

## 运行

```bash
# 启动服务
python main.py

# 或使用 uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

服务启动后：
- 访问 `http://localhost:8000` 打开管理界面
- 访问 `http://localhost:8000/docs` 查看API文档

## 管理界面

前端已内置到 Python 项目中，启动服务后直接访问根路径即可使用，**无需额外打包**。

功能页面：
- **数据总览**: 账号统计、国家分布、粉丝分布
- **账号检测**: 导入并批量检测账号
- **账号列表**: 按状态/国家/粉丝查看账号
- **账号提取**: 按条件筛选并导出账号

## API 说明

### 检测 API

#### 单个账号检测
```
POST /api/check/single
```
请求体:
```json
{
  "username": "用户名",
  "password": "密码",
  "two_fa": "2FA密钥",
  "email": "邮箱",
  "email_password": "邮箱密码",
  "cookie": "Cookie",
  "proxy": "代理"
}
```

#### 批量检测
```
POST /api/check/batch
```

### 分类 API

#### 按状态获取
```
GET /api/accounts/status/{status}
```
状态: 正常、冻结、改密

#### 按国家获取
```
GET /api/accounts/country/{country}
```

#### 按粉丝数量获取
```
GET /api/accounts/followers?min_followers=0&max_followers=9
```

### 提取 API

#### 提取账号
```
POST /api/extract
```
请求体:
```json
{
  "country": "日本",
  "min_followers": 0,
  "max_followers": 9,
  "limit": 100,
  "status": "正常"
}
```

#### 导出账号
```
POST /api/extract/export?format=text
```
导出格式: `用户名----密码----2FA----邮箱----邮箱密码----粉丝数量----国家----年份----是否会员`

### 统计 API

```
GET /api/statistics          # 总览统计
GET /api/statistics/countries # 国家统计
GET /api/statistics/followers # 粉丝区间统计
```

## 账号状态说明

| 状态 | 说明 |
|------|------|
| 正常 | 账号可用，Token验证通过 |
| 冻结 | 账号已被Twitter冻结 |
| 改密 | 需要改密（Token验证失败且邮箱不匹配） |
| 不存在 | 账号不存在 |
| 待检测 | 等待检测 |
| 错误 | 检测过程出错 |

## 注意事项

1. 需要先启动 TID 算法服务（默认 `http://localhost:7700`）
2. 使用代理时支持 SOCKS5 和 HTTP 代理格式
3. Cookie 需要包含 `ct0`、`auth_token`、`twid` 等关键字段

## 项目结构

```
twitter-server/
├── main.py           # FastAPI 主入口
├── config.py         # 配置文件
├── database.py       # 数据库配置
├── models.py         # 数据库模型
├── schemas.py        # API 请求/响应模型
├── services.py       # 业务逻辑层
├── twitter_client.py # Twitter API 客户端
├── utils.py          # 工具函数
├── exceptions.py     # 自定义异常
├── requirements.txt  # 依赖文件
├── static/           # 前端静态文件（Vue3 CDN，无需打包）
│   ├── index.html    # 主入口
│   ├── css/
│   │   └── style.css # 公共样式
│   └── js/
│       ├── api.js       # API 请求封装
│       ├── components.js # 公共组件
│       ├── app.js       # 主应用
│       └── pages/       # 页面组件
│           ├── dashboard.js  # 数据总览
│           ├── check.js      # 账号检测
│           ├── accounts.js   # 账号列表
│           └── extract.js    # 账号提取
└── README.md         # 说明文档
```

