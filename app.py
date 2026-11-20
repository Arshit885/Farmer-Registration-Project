import csv
import io
import os
import sqlite3
from datetime import datetime
from flask import Flask, flash, make_response, redirect, render_template, request, url_for

app = Flask(__name__)
app.secret_key = "arshit-2420678-farmer-registration-secret"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "farmers.db")


def get_db_connection():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS farmers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reg_id TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            village TEXT NOT NULL,
            tehsil TEXT NOT NULL,
            district TEXT NOT NULL,
            state TEXT NOT NULL,
            land_area_kanal REAL NOT NULL,
            crop_type TEXT NOT NULL,
            irrigation_source TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def generate_reg_id(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM farmers")
    count = cur.fetchone()["cnt"]
    year = datetime.now().year
    return f"FRM-{year}-{1001 + count}"


@app.route("/")
def index():
    init_db()
    query = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "All").strip()

    conn = get_db_connection()
    cur = conn.cursor()

    sql = "SELECT * FROM farmers WHERE 1=1"
    params = []

    if query:
        sql += " AND (full_name LIKE ? OR reg_id LIKE ? OR village LIKE ? OR district LIKE ? OR crop_type LIKE ?)"
        like_q = f"%{query}%"
        params.extend([like_q, like_q, like_q, like_q, like_q])

    if status_filter in ("Verified", "Pending"):
        sql += " AND status = ?"
        params.append(status_filter)

    sql += " ORDER BY id DESC"
    cur.execute(sql, params)
    farmers = cur.fetchall()

    cur.execute("SELECT COUNT(*) AS total, COALESCE(SUM(land_area_kanal), 0) AS total_land FROM farmers")
    summary = cur.fetchone()

    cur.execute("SELECT COUNT(*) AS verified_cnt FROM farmers WHERE status = 'Verified'")
    verified_cnt = cur.fetchone()["verified_cnt"]

    cur.execute("SELECT COUNT(*) AS pending_cnt FROM farmers WHERE status = 'Pending'")
    pending_cnt = cur.fetchone()["pending_cnt"]

    conn.close()

    return render_template(
        "index.html",
        farmers=farmers,
        total_farmers=summary["total"],
        verified_count=verified_cnt,
        pending_count=pending_cnt,
        total_land=round(float(summary["total_land"]), 2),
        query=query,
        status_filter=status_filter,
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    init_db()
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        village = request.form.get("village", "").strip()
        tehsil = request.form.get("tehsil", "").strip()
        district = request.form.get("district", "").strip()
        state = request.form.get("state", "Himachal Pradesh").strip()
        land_area_raw = request.form.get("land_area_kanal", "").strip()
        crop_type = request.form.get("crop_type", "").strip()
        irrigation_source = request.form.get("irrigation_source", "").strip()
        status = request.form.get("status", "Pending").strip()

        if not full_name or not phone or not village or not land_area_raw or not crop_type:
            flash("Please fill in all required fields (Name, Phone, Village, Land Area, Crop Type).", "error")
            return render_template("register.html")

        try:
            land_area = float(land_area_raw)
            if land_area <= 0:
                raise ValueError("Land area must be positive.")
        except ValueError:
            flash("Please enter a valid positive number for Land Area (in Kanal).", "error")
            return render_template("register.html")

        conn = get_db_connection()
        reg_id = generate_reg_id(conn)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO farmers
            (reg_id, full_name, phone, village, tehsil, district, state, land_area_kanal, crop_type, irrigation_source, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reg_id,
                full_name,
                phone,
                village,
                tehsil or "N/A",
                district or "N/A",
                state or "N/A",
                land_area,
                crop_type,
                irrigation_source or "Rainfed",
                status if status in ("Verified", "Pending") else "Pending",
                created_at,
            ),
        )
        conn.commit()
        conn.close()

        flash(f"Farmer '{full_name}' registered successfully with ID {reg_id}!", "success")
        return redirect(url_for("index"))

    return render_template("register.html")


@app.route("/toggle-status/<int:farmer_id>", methods=["POST"])
def toggle_status(farmer_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT status FROM farmers WHERE id = ?", (farmer_id,))
    row = cur.fetchone()
    if row:
        new_status = "Pending" if row["status"] == "Verified" else "Verified"
        cur.execute("UPDATE farmers SET status = ? WHERE id = ?", (new_status, farmer_id))
        conn.commit()
        flash(f"Record status updated to {new_status}.", "success")
    conn.close()
    return redirect(url_for("index"))


@app.route("/delete/<int:farmer_id>", methods=["POST"])
def delete_farmer(farmer_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM farmers WHERE id = ?", (farmer_id,))
    conn.commit()
    conn.close()
    flash("Farmer record deleted.", "info")
    return redirect(url_for("index"))


@app.route("/export-csv")
def export_csv():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM farmers ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "ID",
            "Registration ID",
            "Full Name",
            "Phone",
            "Village",
            "Tehsil",
            "District",
            "State",
            "Land Area (Kanal)",
            "Crop Type",
            "Irrigation Source",
            "Status",
            "Registered At",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r["id"],
                r["reg_id"],
                r["full_name"],
                r["phone"],
                r["village"],
                r["tehsil"],
                r["district"],
                r["state"],
                r["land_area_kanal"],
                r["crop_type"],
                r["irrigation_source"],
                r["status"],
                r["created_at"],
            ]
        )

    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=farmer_registrations.csv"
    response.headers["Content-Type"] = "text/csv"
    return response


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
