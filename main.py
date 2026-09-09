# -*- coding: utf-8 -*-
"""针灸病人管理系统 - 主程序 (FastAPI)"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import openpyxl
from io import BytesIO
from datetime import date, datetime
from database import init_db, get_conn

app = FastAPI()
templates = Jinja2Templates(directory="templates")
init_db()

# 医生登录密码
ADMIN_PASSWORD = "8888"

# ============ 页面路由 ============
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

@app.get("/patient", response_class=HTMLResponse)
def patient_page(request: Request):
    return templates.TemplateResponse("patient.html", {"request": request})

# ============ 医生登录 ============
@app.post("/api/login")
def login(data: dict):
    if data.get("password") == ADMIN_PASSWORD:
        return {"ok": True, "msg": "登录成功"}
    raise HTTPException(status_code=403, detail="密码错误")

# ============ 病人管理 ============
@app.post("/api/add_patient")
def add_patient(data: dict):
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    if not name or not phone:
        raise HTTPException(status_code=400, detail="姓名和手机号必填")
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO patients (name, phone) VALUES (?, ?)", (name, phone)
        )
        conn.commit()
        return {"ok": True, "patient_id": cur.lastrowid}
    except Exception as e:
        raise HTTPException(status_code=400, detail="手机号已存在")
    finally:
        conn.close()

@app.get("/api/search_patient")
def search_patient(q: str):
    conn = get_conn()
    cur = conn.execute(
        "SELECT * FROM patients WHERE name LIKE ? OR phone LIKE ?",
        (f"%{q}%", f"%{q}%")
    )
    result = [dict(r) for r in cur.fetchall()]
    conn.close()
    return result

# ============ 充值 ============
@app.post("/api/recharge")
def recharge(data: dict):
    patient_id = data["patient_id"]
    amount = float(data["amount"])
    if amount <= 0:
        raise HTTPException(status_code=400, detail="金额必须大于0")
    conn = get_conn()
    conn.execute("INSERT INTO recharges (patient_id, amount) VALUES (?, ?)", (patient_id, amount))
    conn.execute("UPDATE patients SET balance = balance + ? WHERE id = ?", (amount, patient_id))
    conn.commit()
    conn.close()
    return {"ok": True, "msg": "充值成功"}

# ============ 针灸扣费（医生录入本次价格） ============
@app.post("/api/treat")
def treat(data: dict):
    patient_id = data["patient_id"]
    amount = float(data["amount"])
    today = date.today().isoformat()
    note = data.get("note", "")
    conn = get_conn()
    # 先检查余额是否足够
    p = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    if not p:
        conn.close()
        raise HTTPException(status_code=404, detail="病人不存在")
    if p["balance"] < amount:
        conn.close()
        raise HTTPException(status_code=400, detail="余额不足，请先充值")
    # 检查当天是否已经有针灸记录
    existing = conn.execute(
        "SELECT * FROM treatments WHERE patient_id = ? AND date = ?",
        (patient_id, today)
    ).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="今天已有针灸记录，不能重复扣费")
    # 扣费并记录
    conn.execute("INSERT INTO treatments (patient_id, date, amount, note) VALUES (?, ?, ?, ?)",
                 (patient_id, today, amount, note))
    conn.execute("UPDATE patients SET balance = balance - ? WHERE id = ?", (amount, patient_id))
    conn.commit()
    conn.close()
    return {"ok": True, "msg": "扣费成功"}

# ============ 病人打卡 ============
@app.post("/api/checkin")
def checkin(data: dict):
    phone = data["phone"].strip()
    today = date.today().isoformat()
    conn = get_conn()
    p = conn.execute("SELECT * FROM patients WHERE phone = ?", (phone,)).fetchone()
    if not p:
        conn.close()
        raise HTTPException(status_code=404, detail="未找到该手机号的病人")
    # 查今天是否有针灸记录
    t = conn.execute(
        "SELECT * FROM treatments WHERE patient_id = ? AND date = ?",
        (p["id"], today)
    ).fetchone()
    if not t:
        conn.close()
        raise HTTPException(status_code=400, detail="今天还未记录针灸，请联系医生")
    if t["checked_in"] == 1:
        conn.close()
        raise HTTPException(status_code=400, detail="今天已打卡，明天再来哦")
    # 打卡
    conn.execute("UPDATE treatments SET checked_in = 1 WHERE id = ?", (t["id"],))
    conn.commit()
    conn.close()
    return {"ok": True, "msg": "打卡成功！"}

# ============ 病人查询自己的信息 ============
@app.get("/api/patient_info")
def patient_info(phone: str):
    conn = get_conn()
    p = conn.execute("SELECT * FROM patients WHERE phone = ?", (phone,)).fetchone()
    if not p:
        conn.close()
        raise HTTPException(status_code=404, detail="未找到该手机号的病人")
    today = date.today().isoformat()
    # 查今天是否可打卡及状态
    t = conn.execute(
        "SELECT * FROM treatments WHERE patient_id = ? AND date = ?",
        (p["id"], today)
    ).fetchone()
    checked_in = bool(t["checked_in"]) if t else False
    has_today_record = bool(t) if t else False
    # 最近记录
    records = conn.execute(
        "SELECT * FROM treatments WHERE patient_id = ? ORDER BY date DESC LIMIT 10",
        (p["id"],)
    ).fetchall()
    conn.close()
    return {
        "name": p["name"],
        "phone": p["phone"],
        "balance": p["balance"],
        "checked_in": checked_in,
        "has_today_record": has_today_record,
        "records": [dict(r) for r in records]
    }

# ============ 导出月度表格 ============
@app.get("/api/export")
def export(month: str):
    """month 格式 YYYY-MM"""
    conn = get_conn()
    # 该月所有治疗记录
    rows = conn.execute(
        "SELECT p.name, p.phone, t.date, t.amount, t.checked_in FROM treatments t "
        "JOIN patients p ON t.patient_id = p.id "
        "WHERE substr(t.date, 1, 7) = ?",
        (month,)
    ).fetchall()
    
    # 汇总每个病人的充值/消费/余额
    summaries = conn.execute(
        "SELECT p.name, p.phone, p.balance, "
        "(SELECT COALESCE(SUM(amount), 0) FROM recharges WHERE patient_id = p.id) as total_recharge, "
        "(SELECT COALESCE(SUM(amount), 0) FROM treatments WHERE patient_id = p.id) as total_treat "
        "FROM patients p"
    ).fetchall()
    conn.close()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{month}针灸记录"
    
    # 标题行
    headers = ["姓名", "手机号", "日期", "金额", "打卡状态"]
    ws.append(headers)
    for r in rows:
        ws.append([r["name"], r["phone"], r["date"], r["amount"], "已打卡" if r["checked_in"] else "未打卡"])
    
    # 汇总表
    ws2 = wb.create_sheet("汇总")
    headers2 = ["姓名", "手机号", "总充值", "总消费", "当前余额"]
    ws2.append(headers2)
    for s in summaries:
        ws2.append([s["name"], s["phone"], s["total_recharge"], s["total_treat"], s["balance"]])
    
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    
    # 返回Excel文件
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=zhenjiu_{month}.xlsx"}
    )

# ============ 后台查看某个病人所有记录 ============
@app.get("/api/patient_records")
def patient_records(patient_id: int):
    conn = get_conn()
    p = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    if not p:
        conn.close()
        raise HTTPException(status_code=404, detail="病人不存在")
    recharges = conn.execute(
        "SELECT * FROM recharges WHERE patient_id = ? ORDER BY created_at DESC", (patient_id,)
    ).fetchall()
    treatments = conn.execute(
        "SELECT * FROM treatments WHERE patient_id = ? ORDER BY date DESC", (patient_id,)
    ).fetchall()
    conn.close()
    return {
        "patient": dict(p),
        "recharges": [dict(r) for r in recharges],
        "treatments": [dict(r) for r in treatments]
    }

# ============ 统计（首页显示总人数、今日打卡等） ============
@app.get("/api/stats")
def stats():
    conn = get_conn()
    total_patients = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    today = date.today().isoformat()
    today_checked = conn.execute(
        "SELECT COUNT(*) FROM treatments WHERE date = ? AND checked_in = 1", (today,)
    ).fetchone()[0]
    today_treated = conn.execute(
        "SELECT COUNT(*) FROM treatments WHERE date = ?", (today,)
    ).fetchone()[0]
    conn.close()
    return {
        "total_patients": total_patients,
        "today_checked": today_checked,
        "today_treated": today_treated
    }