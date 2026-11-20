import argparse
import os
from attendance_engine.db import AttendanceDB

def main():
    parser = argparse.ArgumentParser(description="Export Attendance Logs to CSV/Excel")
    parser.add_argument("--out", default="attendance_export.csv", help="Target output file path")
    args = parser.parse_args()

    db = AttendanceDB()
    path = db.export_csv_file(args.out)
    records = db.get_all_records()
    print(f"Exported {len(records)} records to {os.path.abspath(path)}")

if __name__ == "__main__":
    main()
