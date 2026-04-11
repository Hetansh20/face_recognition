"""
Group Photo Attendance Recognizer
===================================
Runs InsightFace on the FULL group photo in ONE PASS — this is the most
reliable approach because:
  - InsightFace's RetinaFace detector needs context around faces to work well
  - face.embedding is computed automatically for every detected face
  - We avoid running a second detection on tiny YOLO crops

YOLO is used OPTIONALLY as a secondary sweep to catch any faces
InsightFace might miss in very crowded images.

Threshold is set to 0.55 (vs 0.45 in streaming mode) since there's no
multi-frame voting in a single group photo — single-shot needs more headroom.
"""

import os
import cv2
import json
import pickle
import numpy as np

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
FACE_DB   = os.path.join(BASE_DIR, "face_database.json")
EMB_CACHE = os.path.join(BASE_DIR, "face_embeddings_insightface.pkl")

# Threshold for a valid match (0.55 gives good recall in single-photo mode)
COSINE_THRESHOLD = 0.55



def _l2_normalize(x: np.ndarray) -> np.ndarray:
    return x / (np.linalg.norm(x) + 1e-10)


def _load_embeddings() -> dict:
    if os.path.exists(EMB_CACHE):
        with open(EMB_CACHE, "rb") as f:
            return pickle.load(f)
    return {}


def _load_face_db() -> dict:
    if os.path.exists(FACE_DB):
        with open(FACE_DB, "r") as f:
            return json.load(f)
    return {}


def _best_match(live_vec: np.ndarray, embeddings: dict):
    """Return (person_id, distance) for best cosine match."""
    if not embeddings:
        return None, 1.0

    dists = []
    for pid, data in embeddings.items():
        if isinstance(data, dict) and "all" in data:
            min_d = min(
                1.0 - float(np.dot(live_vec, sv))
                for sv in data["all"]
            )
            dists.append((pid, min_d))
        elif isinstance(data, dict) and "mean" in data:
            d = 1.0 - float(np.dot(live_vec, data["mean"]))
            dists.append((pid, d))

    if not dists:
        return None, 1.0

    dists.sort(key=lambda x: x[1])
    best_pid, best_d = dists[0]
    print(f"[GroupRecog] Best match: {best_pid} dist={best_d:.4f} (threshold={COSINE_THRESHOLD})")

    if best_d < COSINE_THRESHOLD:
        return best_pid, best_d
    return None, best_d



def process_group_photo(image_bytes: bytes) -> dict:
    """
    Main entry point. Accepts raw JPEG/PNG bytes.
    Returns recognition results and annotated image.
    """
    embeddings = _load_embeddings()
    face_db    = _load_face_db()

    if not embeddings:
        return {"error": "No trained embeddings found. Please train the AI model first (Admin → Faces → Train AI Model)."}

    np_arr = np.frombuffer(image_bytes, np.uint8)
    frame  = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if frame is None:
        return {"error": "Could not decode image."}

    # Scale very large images down to keep inference fast
    h, w = frame.shape[:2]
    if max(h, w) > 1920:
        scale = 1920 / max(h, w)
        frame = cv2.resize(frame, (int(w*scale), int(h*scale)))

    annotated = frame.copy()
    yolo_used = False

    # ── Primary: InsightFace on FULL frame (one pass → all embeddings) ────────
    from insightface.app import FaceAnalysis
    fa = FaceAnalysis(name="buffalo_l")
    try:
        fa.prepare(ctx_id=0, det_thresh=0.35, det_size=(640, 640))
    except Exception:
        fa.prepare(ctx_id=-1, det_thresh=0.35, det_size=(640, 640))

    detected = fa.get(frame)
    print(f"[GroupRecog] InsightFace full-frame: {len(detected)} faces found")

    # Track face centers we have already matched (to avoid duplicates from YOLO)
    matched_centers = set()
    recognized = []

    for face in detected:
        box  = face.bbox.astype(int)
        bbox = [int(box[0]), int(box[1]), int(box[2]), int(box[3])]
        cx   = (bbox[0] + bbox[2]) // 2
        cy   = (bbox[1] + bbox[3]) // 2
        matched_centers.add((cx // 20, cy // 20))  # 20px grid cell

        live_vec = _l2_normalize(face.embedding.astype(np.float32))
        pid, dist = _best_match(live_vec, embeddings)

        if pid:
            info       = face_db.get(pid, {})
            confidence = round((1.0 - dist) * 100, 1)
            recognized.append({
                "person_id":   pid,
                "name":        info.get("name", pid),
                "employee_id": info.get("employee_id", ""),
                "confidence":  confidence,
                "bbox":        bbox,
            })
            _draw_box(annotated, bbox, info.get("name", pid), confidence)
            print(f"[GroupRecog] ✓ {info.get('name', pid)} conf={confidence}%")
        else:
            _draw_box(annotated, bbox, None, None)
            print(f"[GroupRecog] ✗ Unknown — dist={dist:.4f}")

    unrecognized = len(detected) - len(recognized)

    # ── Optional YOLO sweep: catches small/background faces InsightFace missed ─
    yolo_model = os.path.join(BASE_DIR, "yolov8n-face.pt")
    if os.path.exists(yolo_model) and len(detected) > 0:
        try:
            from ultralytics import YOLO
            yolo = YOLO(yolo_model)
            results = yolo(frame, verbose=False, conf=0.4)[0]
            extra = 0
            for box in results.boxes.xyxy.cpu().numpy():
                x1, y1, x2, y2 = map(int, box[:4])
                cx, cy = (x1+x2)//2, (y1+y2)//2
                cell = (cx//20, cy//20)
                if cell in matched_centers:
                    continue  # already processed this face
                # Extract crop with padding and get InsightFace embedding
                pad  = 20
                crop = frame[max(0,y1-pad):min(h,y2+pad), max(0,x1-pad):min(w,x2+pad)]
                faces_in_crop = fa.get(crop)
                if faces_in_crop:
                    best_crop = max(faces_in_crop, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
                    lv = _l2_normalize(best_crop.embedding.astype(np.float32))
                    pid2, dist2 = _best_match(lv, embeddings)
                    bbox2 = [x1, y1, x2, y2]
                    matched_centers.add(cell)
                    if pid2:
                        info = face_db.get(pid2, {})
                        confidence = round((1.0 - dist2) * 100, 1)
                        recognized.append({
                            "person_id":   pid2,
                            "name":        info.get("name", pid2),
                            "employee_id": info.get("employee_id", ""),
                            "confidence":  confidence,
                            "bbox":        bbox2,
                        })
                        _draw_box(annotated, bbox2, info.get("name", pid2), confidence)
                        extra += 1
                    else:
                        unrecognized += 1
                        _draw_box(annotated, bbox2, None, None)
            yolo_used = extra > 0
        except Exception as e:
            print(f"[GroupRecog] YOLO sweep skipped: {e}")

    return {
        "recognized":         recognized,
        "unrecognized_count": max(0, unrecognized),
        "total_faces":        len(detected),
        "annotated_image":    _encode_image(annotated),
        "yolo_used":          yolo_used,
    }


def _draw_box(frame, bbox, name, confidence):
    x1, y1, x2, y2 = bbox
    color = (46, 160, 67) if name else (218, 54, 51)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    label = f"{name}  {confidence}%" if name else "Unknown"
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
    cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 8, y1), color, -1)
    cv2.putText(frame, label, (x1 + 4, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)


def _encode_image(frame: np.ndarray) -> str:
    import base64
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()
