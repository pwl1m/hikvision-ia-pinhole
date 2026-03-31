#!/usr/bin/env python3
import argparse
import json
import sqlite3
from pathlib import Path


DEFAULT_DB = Path("volumes/faces/detections.db")


def main():
    parser = argparse.ArgumentParser(description="Mostra comparacoes salvas pelo detector")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Caminho para o arquivo detections.db")
    parser.add_argument("--limit", type=int, default=10, help="Quantidade de registros")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT timestamp, camera, event_id, event_type, face_detected, occluded,
               occlusion_type, confidence, recognized_subject, recognition_confidence,
               compreface_status, compreface_candidates, snapshot_path, face_roi_path
        FROM detections
        ORDER BY id DESC
        LIMIT ?
        """,
        (args.limit,),
    ).fetchall()
    conn.close()

    for index, row in enumerate(rows, start=1):
        print(f"Registro {index}")
        print(f"  timestamp: {row['timestamp']}")
        print(f"  camera: {row['camera']}")
        print(f"  event_id: {row['event_id']}")
        print(f"  event_type: {row['event_type']}")
        print(f"  face_detected: {row['face_detected']}")
        print(f"  occluded: {row['occluded']}")
        print(f"  occlusion_type: {row['occlusion_type']}")
        print(f"  face_confidence: {row['confidence']}")
        print(f"  recognized_subject: {row['recognized_subject']}")
        print(f"  recognition_confidence: {row['recognition_confidence']}")
        print(f"  compreface_status: {row['compreface_status']}")
        candidates = row['compreface_candidates']
        if candidates:
            parsed = json.loads(candidates)
            print("  candidates:")
            for candidate in parsed:
                print(
                    f"    - subject={candidate.get('subject')} similarity={candidate.get('similarity')}"
                )
        else:
            print("  candidates: []")
        print(f"  snapshot_path: {row['snapshot_path']}")
        print(f"  face_roi_path: {row['face_roi_path']}")
        print()


if __name__ == "__main__":
    main()