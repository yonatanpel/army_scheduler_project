import streamlit as st
import sqlite3
import pandas as pd
from ortools.sat.python import cp_model

# ==========================================
# 1. אתחול בסיס הנתונים (SQLite) - סימולציית 100 לוחמים
# ==========================================
def init_db():
    conn = sqlite3.connect("army_schedule.db")
    cursor = conn.cursor()
    
    # יצירת טבלאות
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS soldiers (
            soldier_id INTEGER PRIMARY KEY,
            name TEXT,
            role TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS constraints (
            soldier_id INTEGER,
            day INTEGER,
            is_requested_home INTEGER,
            PRIMARY KEY (soldier_id, day)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS final_schedule (
            soldier_id INTEGER,
            day INTEGER,
            is_home INTEGER,
            PRIMARY KEY (soldier_id, day)
        )
    """)
    
    # בדיקה האם בסיס הנתונים ריק - אם כן, מייצרים 100 לוחמים גנריים
    cursor.execute("SELECT COUNT(*) FROM soldiers")
    if cursor.fetchone()[0] == 0:
        sample_soldiers = []
        
        # יצירת 10 מפקדים (מ"פים, מפל"ג, מפקדי מחלקות וצוותים)
        for i in range(1, 11):
            sample_soldiers.append((i, f"מפקד {i}", "Commander"))
            
        # יצירת 8 חובשים פלוגתיים
        for i in range(11, 19):
            sample_soldiers.append((i, f"חובש {i-10}", "Medic"))
            
        # יצירת 12 נהגים מבצעיים (נהגי האמרים/נגמ"שים)
        for i in range(19, 31):
            sample_soldiers.append((i, f"נהג {i-18}", "Driver"))
            
        # יצירת 70 לוחמי סד"כ רגיל
        for i in range(31, 101):
            sample_soldiers.append((i, f"לוחם {i-30}", "Standard"))
            
        cursor.executemany("INSERT INTO soldiers VALUES (?, ?, ?)", sample_soldiers)
        
        # הזנת אילוצי פרט אקראיים ראשוניים (למשל: כמה לוחמים שחייבים לצאת בימים מסוימים)
        initial_constraints = [
            (35, 3, 1), (42, 5, 1), (12, 7, 1), (5, 2, 1), (88, 12, 1), (15, 4, 1)
        ]
        cursor.executemany("INSERT INTO constraints VALUES (?, ?, 1)", initial_constraints)
        
    conn.commit()
    conn.close()

init_db()

# אופק תכנון מורחב התואם פלוגה - 14 ימי תעסוקה מבצעית (שבועיים)
DAYS = list(range(1, 15))

# ==========================================
# 2. מנוע האופטימיזציה המתמטי (CP-SAT) ל-100 לוחמים
# ==========================================
def run_optimization():
    conn = sqlite3.connect("army_schedule.db")
    soldiers_df = pd.read_sql_query("SELECT * FROM soldiers", conn)
    constraints_df = pd.read_sql_query("SELECT * FROM constraints", conn)
    conn.close()
    
    model = cp_model.CpModel()
    
    # מטריצת משתני החלטה: X[i, t] עבור 100 לוחמים ו-14 ימים (1,400 משתנים בוליאניים)
    X = {}
    for _, s in soldiers_df.iterrows():
        for t in DAYS:
            X[(s['soldier_id'], t)] = model.NewBoolVar(f"X_{s['soldier_id']}_{t}")
            
    # --- הגדרת אילוצים מבצעיים מותאמים לפלוגה (100 איש) ---
    for t in DAYS:
        # אילוץ 1: סד"כ פלוגתי מינימלי בבסיס (חובה לפחות 65 לוחמים בבסיס בכל יום -> מקסימום 35 בחופשה)
        model.Add(sum(X[(s['soldier_id'], t)] for _, s in soldiers_df.iterrows()) <= 35)
        
        # אילוץ 2: שמירת שלד פיקודי (לפחות 6 מפקדים מתוך 10 חייבים להישאר בבסיס -> מקסימום 4 בחופשה)
        commanders = soldiers_df[soldiers_df['role'] == 'Commander']
        model.Add(sum(X[(c['soldier_id'], t)] for _, c in commanders.iterrows()) <= 4)
        
        # אילוץ 3: כשירות רפואית (לפחות 4 חובשים מתוך 8 בבסיס בכל יום -> מקסימום 4 בחופשה)
        medics = soldiers_df[soldiers_df['role'] == 'Medic']
        model.Add(sum(X[(m['soldier_id'], t)] for _, m in medics.iterrows()) <= 4)

        # אילוץ 4: כשירות ניוד ויציאה למשימות (לפחות 7 נהגים מתוך 12 בבסי