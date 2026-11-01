from app import create_app
from app.db import create_db

db = create_db("preadmission.db")

# Synthetic demo bookings so you can try the API straight away.
if db.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 0:
    db.executemany(
        "INSERT INTO bookings (hospital_id, patient_name) VALUES (?, ?)",
        [("H1", "Test Patient One"), ("H1", "Test Patient Two"), ("H2", "Test Patient Three")],
    )
    db.commit()

app = create_app(db)

if __name__ == "__main__":
    app.run(port=3000)
