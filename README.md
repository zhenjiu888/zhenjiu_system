# 针灸病人管理系统

一个用于针灸诊所的病人打卡与费用管理系统。

## 功能
- **医生后台**：登录（密码 8888）、添加病人、搜索病人、充值、扣费（录入本次价格）、查看记录、导出月度Excel
- **病人端**：输入手机号查看余额和记录、当日打卡（防重复、次日解锁）
- **余额提醒**：余额不足时后台和病人端都会提示

## 技术栈
- 后端：FastAPI（Python）
- 数据库：SQLite（zhenjiu.db）
- 前端：HTML + JavaScript

## 运行方式
```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

打开浏览器访问 `http://localhost:8000`

## 部署（Render.com）
1. 将本目录推送到 GitHub 仓库
2. 在 Render 创建 Web Service，连接该仓库
3. 构建命令：`pip install -r requirements.txt`
4. 启动命令：`uvicorn main:app --host 0.0.0.0 --port $PORT`
