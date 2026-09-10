# -*- coding: utf-8 -*-
"""针灸病人管理系统"""
from datetime import datetime, date
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from database import init_db, get_conn

app = FastAPI()
templates = Jinja2Templates(directory="templates")
init_db()

ADMIN_PASSWORD = "8888"

@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/admin")
def admin_page(request: Request):
    return templates.TemplateResponse(request=request, name="admin.html")

@app.get("/patient")
def patient_page(request: Request):
    return templates.TemplateResponse(request=request, name="patient.html")

# 医生登录
@app.post("/api/login")
def login(data: dict):
    if data.get("password") == ADMIN_PASSWORD:
        return {"success": True}
    return {"success": False, "msg": "密码错误"}

# 添加病人
@app.post("/api/add_patient")
def add_patient(data: dict):
    conn = get_conn()
    name = data.get("name")
    phone = data.get("phone")
    balance = data.get("balance", 0)
    conn.execute("INSERT INTO patients (name, phone, balance, created_at) VALUES (?, ?, ?, ?)",
                 (name, phone, balance, date.today().isoformat()))
    conn.commit()
    conn.close()
    return {"success": True}

# 搜索病人（直接返回数组，前端好处理）
@app.get("/api/search_patient")
def search_patient(q: str):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM patients WHERE name LIKE ? OR phone LIKE ?",
                        (f"%{q}%", f"%{q}%")).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# 充值
@app.post("/api/recharge")
def recharge(data: dict):
    conn = get_conn()
    pid = data.get("patient_id")
    amount = data.get("amount", 0)
    conn.execute("UPDATE patients SET balance = balance + ? WHERE id = ?", (amount, pid))
    conn.commit()
    conn.close()
    return {"success": True}

# 针灸扣费（每天只能扣一次，金额可由前端传入）
@app.post("/api/treat")
def treat(data: dict):
    conn = get_conn()
    pid = data.get("patient_id")
    note = data.get("note", "")
    today = date.today().isoformat()
    checked = conn.execute(
        "SELECT COUNT(*) FROM treatments WHERE patient_id = ? AND date = ? AND checked_in = 1",
        (pid, today)).fetchone()[0]
    if checked > 0:
        conn.close()
        return {"success": False, "msg": "今天已治疗过", "detail": "今天已治疗过"}
    # 优先用前端传的金额，没传就用 settings 里的默认价
    amount = data.get("amount")
    if amount is None:
        price_row = conn.execute("SELECT price FROM settings").fetchone()
        amount = price_row[0] if price_row else 50
    conn.execute("INSERT INTO treatments (patient_id, date, amount, checked_in, note, created_at) VALUES (?, ?, ?, 1, ?, ?)",
                 (pid, today, amount, note, datetime.now().isoformat()))
    conn.execute("UPDATE patients SET balance = balance - ? WHERE id = ?", (amount, pid))
    conn.commit()
    conn.close()
    return {"success": True, "price": amount}

# 打卡
@app.post("/api/checkin")
def checkin(data: dict):
    conn = get_conn()
    pid = data.get("patient_id")
    today = date.today().isoformat()
    conn.execute("INSERT INTO treatments (patient_id, date, checked_in, created_at) VALUES (?, ?, 1, ?)",
                 (pid, today, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"success": True}

# 病人查询信息
@app.get("/api/patient_info")
def patient_info(patient_id: int):
    conn = get_conn()
    p = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    if not p:
        conn.close()
        return {"patient": None}
    records = conn.execute(
        "SELECT * FROM treatments WHERE patient_id = ? ORDER BY date DESC", (patient_id,)).fetchall()
    conn.close()
    return {"patient": dict(p), "records": [dict(r) for r in records]}

@app.get("/api/export")
def export_excel(month: str = None):
    from openpyxl import Workbook
    conn = get_conn()
    rows = conn.execute("SELECT * FROM patients").fetchall()
    conn.close()
    wb = Workbook()
    ws = wb.active
    ws.title = "病人"
    ws.append(["姓名", "电话", "余额"])
    for r in rows:
        ws.append([r["name"], r["phone"], r["balance"]])_
    import io
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=patients.xlsx"})

# 病人记录
@app.get("/api/patient_records")
def patient_records(patient_id: int):
    conn = get_conn()
    p = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    if not p:
        conn.close()
        return {"patient": None}
    records = conn.execute(
        "SELECT * FROM treatments WHERE patient_id = ? ORDER BY date DESC", (patient_id,)).fetchall()
    conn.close()
    return {
        "patient": dict(p),
        "treatments": [dict(r) for r in records],
        "records": [dict(r) for r in records],
    }

@app.get("/api/stats")
def stats():
    conn = get_conn()
    total_patients = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    today = date.today().isoformat()
    today_checked = conn.execute(
        "SELECT COUNT(*) FROM treatments WHERE date = ? AND checked_in = 1", (today,)).fetchone()[0]
    today_treated = conn.execute(
        "SELECT COUNT(*) FROM treatments WHERE date = ?", (today,)).fetchone()[0]
    conn.close()
    return {"total_patients": total_patients, "today_checked": today_checked, "today_treated": today_treated}
