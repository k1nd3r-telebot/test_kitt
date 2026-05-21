from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import sqlite3
from datetime import datetime

app = FastAPI(title="Kitting API")


from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # în dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
DB_NAME = "kitting.db"


# =========================
# DATABASE
# =========================

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # warehouse
    cur.execute("""
    CREATE TABLE IF NOT EXISTS warehouse (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location TEXT NOT NULL,
        part_no TEXT NOT NULL,
        qty INTEGER NOT NULL,
        insert_date TEXT NOT NULL
    )
    """)

    # bom
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bom (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        part_no TEXT NOT NULL,
        part_int TEXT NOT NULL
    )
    """)

    # routing
    cur.execute("""
    CREATE TABLE IF NOT EXISTS routing (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        part_no TEXT NOT NULL UNIQUE,
        description TEXT
    )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================
# MODELS
# =========================

class WarehouseItem(BaseModel):
    location: str
    part_no: str
    qty: int


class RemoveStock(BaseModel):
    part_no: str
    qty: int


class BomItem(BaseModel):
    part_no: str
    part_int: str


class RoutingItem(BaseModel):
    part_no: str
    description: str


# =========================
# WAREHOUSE
# =========================

@app.post("/warehouse/add")
def add_warehouse_item(item: WarehouseItem):

    if item.qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be > 0")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO warehouse (location, part_no, qty, insert_date)
    VALUES (?, ?, ?, ?)
    """, (
        item.location.upper(),
        item.part_no.upper(),
        item.qty,
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": "Part added"
    }


@app.post("/warehouse/import")
def import_warehouse(items: List[WarehouseItem]):

    conn = get_db()
    cur = conn.cursor()

    data = []

    for item in items:

        if item.qty <= 0:
            continue

        data.append((
            item.location.upper(),
            item.part_no.upper(),
            item.qty,
            datetime.now().isoformat()
        ))

    cur.executemany("""
    INSERT INTO warehouse (location, part_no, qty, insert_date)
    VALUES (?, ?, ?, ?)
    """, data)

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "inserted": len(data)
    }


@app.post("/warehouse/remove")
def remove_stock(data: RemoveStock):

    if data.qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be > 0")

    conn = get_db()
    cur = conn.cursor()

    # total stock
    cur.execute("""
    SELECT COALESCE(SUM(qty), 0) as total
    FROM warehouse
    WHERE part_no = ?
    """, (data.part_no.upper(),))

    total = cur.fetchone()["total"]

    if total < data.qty:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"Not enough stock. Available: {total}"
        )

    qty_to_remove = data.qty

    # oldest stock first (FIFO)
    cur.execute("""
    SELECT id, qty
    FROM warehouse
    WHERE part_no = ?
    ORDER BY insert_date ASC
    """, (data.part_no.upper(),))

    rows = cur.fetchall()

    for row in rows:

        row_id = row["id"]
        row_qty = row["qty"]

        if qty_to_remove <= 0:
            break

        if row_qty <= qty_to_remove:

            cur.execute("""
            DELETE FROM warehouse
            WHERE id = ?
            """, (row_id,))

            qty_to_remove -= row_qty

        else:

            new_qty = row_qty - qty_to_remove

            cur.execute("""
            UPDATE warehouse
            SET qty = ?
            WHERE id = ?
            """, (new_qty, row_id))

            qty_to_remove = 0

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "removed_qty": data.qty
    }


@app.get("/warehouse")
def get_warehouse():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM warehouse
    ORDER BY insert_date DESC
    """)

    rows = [dict(row) for row in cur.fetchall()]

    conn.close()

    return rows


@app.get("/warehouse/stock/{part_no}")
def get_stock(part_no: str):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT COALESCE(SUM(qty), 0) as total
    FROM warehouse
    WHERE part_no = ?
    """, (part_no.upper(),))

    total = cur.fetchone()["total"]

    conn.close()

    return {
        "part_no": part_no.upper(),
        "stock": total
    }


# =========================
# BOM
# =========================

@app.post("/bom/add")
def add_bom(item: BomItem):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO bom (part_no, part_int)
    VALUES (?, ?)
    """, (
        item.part_no.upper(),
        item.part_int.upper()
    ))

    conn.commit()
    conn.close()

    return {
        "status": "success"
    }


@app.get("/bom/{part_no}")
def get_bom(part_no: str):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM bom
    WHERE part_no = ?
    """, (part_no.upper(),))

    rows = [dict(row) for row in cur.fetchall()]

    conn.close()

    return rows


# =========================
# ROUTING
# =========================

@app.post("/routing/add")
def add_routing(item: RoutingItem):

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute("""
        INSERT INTO routing (part_no, description)
        VALUES (?, ?)
        """, (
            item.part_no.upper(),
            item.description
        ))

        conn.commit()

    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="part_no already exists"
        )

    conn.close()

    return {
        "status": "success"
    }


@app.get("/routing")
def get_routing():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM routing
    """)

    rows = [dict(row) for row in cur.fetchall()]

    conn.close()

    return rows


# =========================
# KITTING
# =========================

@app.post("/kitting/create/{part_no}/{qty}")
def create_kit(part_no: str, qty: int):

    conn = get_db()
    cur = conn.cursor()

    part_no = part_no.upper()

    # =====================
    # 1. GET BOM
    # =====================
    cur.execute("""
        SELECT part_int
        FROM bom
        WHERE part_no = ?
    """, (part_no,))

    bom_rows = cur.fetchall()

    if not bom_rows:
        conn.close()
        raise HTTPException(status_code=404, detail="BOM not found")

    bom = [row["part_int"] for row in bom_rows]

    # =====================
    # 2. GET ROUTING
    # =====================
    cur.execute("""
        SELECT part_no, description
        FROM routing
        WHERE part_no = ?
    """, (part_no,))

    routing_row = cur.fetchone()
    routing = dict(routing_row) if routing_row else None

    # =====================
    # 3. STOCK PRECHECK
    # =====================
    missing = []

    for component in bom:

        cur.execute("""
            SELECT COALESCE(SUM(qty), 0) as total
            FROM warehouse
            WHERE part_no = ?
        """, (component,))

        stock = cur.fetchone()["total"]

        if stock < qty:
            missing.append({
                "part_no": component,
                "required": qty,
                "available": stock
            })

    if missing:
        conn.close()
        return {
            "status": "failed",
            "part_no": part_no,
            "qty": qty,
            "bom": bom,
            "routing": routing,
            "missing": missing
        }

    # =====================
    # 4. FIFO CONSUME
    # =====================
    picking_list = []

    try:
        for component in bom:

            remaining = qty

            cur.execute("""
                SELECT id, part_no, qty, location
                FROM warehouse
                WHERE part_no = ?
                AND qty > 0
                ORDER BY id ASC
            """, (component,))

            rows = cur.fetchall()

            for row in rows:

                if remaining <= 0:
                    break

                wh_id = row["id"]
                available = row["qty"]

                take = min(available, remaining)

                # =====================
                # OPTIMIZED DELETE / UPDATE
                # =====================
                if take == available:
                    cur.execute("""
                        DELETE FROM warehouse
                        WHERE id = ?
                    """, (wh_id,))
                else:
                    cur.execute("""
                        UPDATE warehouse
                        SET qty = qty - ?
                        WHERE id = ?
                    """, (take, wh_id))

                picking_list.append({
                    "location": row["location"],
                    "part_no": row["part_no"],
                    "qty_to_pick": take
                })

                remaining -= take

            if remaining > 0:
                conn.rollback()
                conn.close()

                return {
                    "status": "failed",
                    "part_no": part_no,
                    "qty": qty,
                    "error": f"Insufficient stock for {component}",
                    "missing_qty": remaining
                }

        conn.commit()

    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        conn.close()

    # =====================
    # 5. RESPONSE
    # =====================
    return {
        "status": "success",
        "part_no": part_no,
        "qty": qty,
        "bom": bom,
        "routing": routing,
        "missing": [],
        "picking": picking_list
    }

# =========================
# ROOT
# =========================

@app.get("/")
def root():
    return {
        "app": "Kitting API",
        "status": "running"
    }