#!/usr/bin/env python3
import argparse
import sqlite3
from pathlib import Path


DEFAULT_DB = Path("volumes/faces/detections.db")


def main():
    parser = argparse.ArgumentParser(description="Lista os desconhecidos acompanhados automaticamente")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Caminho do detections.db")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT subject, created_at, last_seen_at, sightings, last_event_id, best_face_path, source_camera
        FROM unknown_subjects
        ORDER BY id DESC
        """
    ).fetchall()
    conn.close()

    if not rows:
        print("Nenhum desconhecido acompanhado ainda.")
        return

    for row in rows:
        print(f"subject: {row['subject']}")
        print(f"  created_at: {row['created_at']}")
        print(f"  last_seen_at: {row['last_seen_at']}")
        print(f"  sightings: {row['sightings']}")
        print(f"  last_event_id: {row['last_event_id']}")
        print(f"  best_face_path: {row['best_face_path']}")
        print(f"  source_camera: {row['source_camera']}")
        print()


if __name__ == "__main__":
    main()