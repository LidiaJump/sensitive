import os
import uuid
import json
import threading
import time
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional

from config import UPLOAD_DIR, OUTPUT_DIR, STATIC_DIR, TEMPLATE_DIR, AUTO_CLEAN_ON_TASK
from .excel_handler import read_excel, write_excel, auto_detect_columns, save_job_data, load_job_data
from .core.engine import DesensitizationEngine
from .core.cleaner import clean_on_task
from .core.rules import (
    mask_id_card, mask_phone, mask_certificate,
    mask_social_security, mask_address,
)

app = FastAPI(title="政务工单脱敏系统", version="1.2.0")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

jobs = {}


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls 文件")

    # 每次上传前清理过期文件
    clean_on_task()

    job_id = str(uuid.uuid4())[:8]
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}_{file.filename}")
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    headers, rows = read_excel(file_path)
    detected_config = auto_detect_columns(headers)

    jobs[job_id] = {
        "job_id": job_id,
        "filename": file.filename,
        "file_path": file_path,
        "headers": headers,
        "original_rows": rows,
        "detected_config": detected_config,
        "status": "uploaded",
        "created_at": datetime.now().isoformat(),
    }

    save_job_data(job_id, jobs[job_id], OUTPUT_DIR)

    return {
        "job_id": job_id,
        "filename": file.filename,
        "total_rows": len(rows),
        "total_columns": len(headers),
        "headers": headers,
        "detected_config": detected_config,
        "sample_row": rows[0] if rows else {},
    }


@app.post("/api/desensitize/{job_id}")
async def desensitize(
    job_id: str,
    name_columns: Optional[str] = Form(None),
    phone_columns: Optional[str] = Form(None),
    id_card_columns: Optional[str] = Form(None),
    address_columns: Optional[str] = Form(None),
    text_columns: Optional[str] = Form(None),
    enable_id_card: bool = Form(True),
    enable_phone: bool = Form(True),
    enable_name: bool = Form(True),
    enable_salutation: bool = Form(True),
    enable_address: bool = Form(True),
):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="任务不存在")

    job = jobs[job_id]

    config = {
        "name_columns": name_columns.split(",") if name_columns else job["detected_config"]["name_columns"],
        "phone_columns": phone_columns.split(",") if phone_columns else job["detected_config"]["phone_columns"],
        "id_card_columns": id_card_columns.split(",") if id_card_columns else job["detected_config"]["id_card_columns"],
        "address_columns": address_columns.split(",") if address_columns else job["detected_config"].get("address_columns", []),
        "text_columns": text_columns.split(",") if text_columns else job["detected_config"]["text_columns"],
        "enable_rules": {
            "id_card": enable_id_card,
            "phone": enable_phone,
            "name": enable_name,
            "salutation": enable_salutation,
            "address": enable_address,
        },
    }

    engine = DesensitizationEngine(config)
    processed_rows, result = engine.process_batch(job["original_rows"])

    job["processed_rows"] = processed_rows
    job["config"] = config
    job["result"] = {
        "total_rows": result.total_rows,
        "total_hits": result.total_hits,
        "hits_by_rule": result.hits_by_rule,
        "audit_entries": result.audit_entries,
        "scan_passed": result.scan_passed,
        "scan_warnings": result.scan_warnings,
        "duration_ms": result.duration_ms,
    }
    job["status"] = "completed"

    save_job_data(job_id, job, OUTPUT_DIR)

    return {
        "job_id": job_id,
        "status": "completed",
        "total_rows": result.total_rows,
        "total_hits": result.total_hits,
        "hits_by_rule": result.hits_by_rule,
        "scan_passed": result.scan_passed,
        "scan_warnings": result.scan_warnings,
        "duration_ms": result.duration_ms,
        "audit_count": len(result.audit_entries),
    }


@app.get("/api/preview/{job_id}")
async def preview(job_id: str, limit: int = 10):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="任务不存在")

    job = jobs[job_id]
    if "processed_rows" not in job:
        raise HTTPException(status_code=400, detail="尚未完成脱敏处理")

    limit = min(limit, len(job["original_rows"]))
    original = job["original_rows"][:limit]
    processed = job["processed_rows"][:limit]

    diff_columns = []
    for h in job["headers"]:
        has_diff = any(
            str(original[i].get(h, "")) != str(processed[i].get(h, ""))
            for i in range(limit)
        )
        if has_diff:
            diff_columns.append(h)

    return {
        "job_id": job_id,
        "headers": job["headers"],
        "diff_columns": diff_columns,
        "rows": [
            {
                "index": i,
                "original": original[i],
                "processed": processed[i],
            }
            for i in range(limit)
        ],
    }


@app.get("/api/audit/{job_id}")
async def get_audit(job_id: str, rule_id: Optional[str] = None, limit: int = 50):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="任务不存在")

    job = jobs[job_id]
    if "result" not in job:
        raise HTTPException(status_code=400, detail="尚未完成脱敏处理")

    entries = job["result"]["audit_entries"]
    if rule_id:
        entries = [e for e in entries if e["rule_id"] == rule_id]

    return {
        "job_id": job_id,
        "total": len(entries),
        "entries": entries[:limit],
        "hits_by_rule": job["result"]["hits_by_rule"],
        "scan_passed": job["result"]["scan_passed"],
        "scan_warnings": job["result"]["scan_warnings"],
    }


@app.post("/api/fix/{job_id}")
async def fix_suspicious(job_id: str, request: Request):
    """人工确认疑似项后，对选中的位置做针对性脱敏修复。

    body: {"items": [{"row": 479, "column": "备注", "type": "id_card"}, ...]}
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="任务不存在")

    job = jobs[job_id]
    if "processed_rows" not in job:
        raise HTTPException(status_code=400, detail="尚未完成脱敏处理")

    body = await request.json()
    items = body.get("items", [])
    if not items:
        return {"fixed": 0, "message": "未选择需要修复的疑似项"}

    # 修复函数映射
    FIXERS = {
        "id_card": mask_id_card,
        "phone": mask_phone,
        "certificate": mask_certificate,
        "social_security": mask_social_security,
        "address": mask_address,
    }

    fixed = 0
    fixed_entries = []
    for item in items:
        row = item.get("row")
        col = item.get("column")
        ftype = item.get("type")
        if row is None or col is None or ftype not in FIXERS:
            continue
        if row < 0 or row >= len(job["processed_rows"]):
            continue
        cur = job["processed_rows"][row].get(col)
        if not cur:
            continue
        text = str(cur)
        # 先还原高置信度规则？不——直接对当前文本跑目标规则，跳过已打星内容
        result = FIXERS[ftype](text)
        if result.hit_count > 0:
            job["processed_rows"][row][col] = result.masked_text
            fixed += 1
            fixed_entries.append({
                "row": row,
                "row_no": row + 1,
                "column": col,
                "type": ftype,
                "hit_count": result.hit_count,
            })

    # 重新扫描完整性
    engine = DesensitizationEngine(job.get("config", {}))
    warnings = engine.scan_completeness(job["processed_rows"])
    job["result"]["scan_warnings"] = warnings
    job["result"]["scan_passed"] = len(warnings) == 0
    save_job_data(job_id, job, OUTPUT_DIR)

    return {
        "fixed": fixed,
        "fixed_entries": fixed_entries,
        "scan_warnings": warnings,
        "scan_passed": len(warnings) == 0,
    }


@app.get("/api/download/{job_id}")
async def download(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="任务不存在")

    job = jobs[job_id]
    if "processed_rows" not in job:
        raise HTTPException(status_code=400, detail="尚未完成脱敏处理")

    original_name = job["filename"]
    base_name = os.path.splitext(original_name)[0]
    output_filename = f"{base_name}_脱敏后.xlsx"
    output_path = os.path.join(OUTPUT_DIR, f"{job_id}_{output_filename}")

    write_excel(output_path, job["headers"], job["processed_rows"])

    return FileResponse(
        output_path,
        filename=output_filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/jobs")
async def list_jobs():
    return {
        "jobs": [
            {
                "job_id": jid,
                "filename": j["filename"],
                "status": j["status"],
                "total_rows": len(j.get("original_rows", [])),
                "total_hits": j.get("result", {}).get("total_hits", 0),
                "created_at": j.get("created_at", ""),
            }
            for jid, j in jobs.items()
        ]
    }


# ============================================================
# 模板管理
# ============================================================

@app.get("/api/templates")
async def list_templates():
    """列出所有已保存的列映射模板。"""
    templates = []
    for f in TEMPLATE_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                t = json.load(fp)
                templates.append({
                    "id": f.stem,
                    "name": t.get("name", f.stem),
                    "columns": t.get("columns", []),
                    "created_at": t.get("created_at", ""),
                })
        except (json.JSONDecodeError, OSError):
            continue
    templates.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"templates": templates}


@app.post("/api/templates")
async def save_template(
    name: str = Form(...),
    name_columns: str = Form(""),
    phone_columns: str = Form(""),
    id_card_columns: str = Form(""),
    address_columns: str = Form(""),
    text_columns: str = Form(""),
):
    """保存列映射模板。"""
    template_id = str(uuid.uuid4())[:8]
    template = {
        "id": template_id,
        "name": name.strip(),
        "columns": {
            "name_columns": [c for c in name_columns.split(",") if c],
            "phone_columns": [c for c in phone_columns.split(",") if c],
            "id_card_columns": [c for c in id_card_columns.split(",") if c],
            "address_columns": [c for c in address_columns.split(",") if c],
            "text_columns": [c for c in text_columns.split(",") if c],
        },
        "created_at": datetime.now().isoformat(),
    }
    path = TEMPLATE_DIR / f"{template_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)
    return {"id": template_id, "name": template["name"], "status": "saved"}


@app.delete("/api/templates/{template_id}")
async def delete_template(template_id: str):
    """删除模板。"""
    path = TEMPLATE_DIR / f"{template_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="模板不存在")
    path.unlink()
    return {"status": "deleted"}


@app.post("/api/shutdown")
async def shutdown():
    """优雅关闭后端服务（由前端"退出程序"按钮调用）。

    延迟 0.5 秒后设置 server.should_exit，让本响应先返回前端。
    """
    server = getattr(app.state, "server", None)
    if server is None:
        # 开发模式（uvicorn.run）下无法优雅关闭，直接退出进程
        import os
        threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0)), daemon=True).start()
        return {"status": "shutting_down"}
    threading.Thread(
        target=lambda: (time.sleep(0.5), setattr(server, "should_exit", True)),
        daemon=True,
    ).start()
    return {"status": "shutting_down"}
