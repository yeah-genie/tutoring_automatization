"""
이미지/PDF 전처리 모듈.
- 이미지 품질 점수 계산 (흐림, 밝기 등)
- OpenCV로 기울기 보정 및 대비 향상
- PDF를 페이지별 이미지로 변환
- base64 인코딩 (Claude API 전송용)
"""

import base64
import logging
from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

MAX_IMAGE_DIMENSION = 2048  # Claude Vision 권장 최대 크기


def compute_quality_score(image_path: Path) -> float:
    """
    이미지 품질 점수 계산 (0~100).
    흐림(라플라시안 분산) + 밝기 기반.
    """
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0.0

    blur_score = cv2.Laplacian(img, cv2.CV_64F).var()
    normalized_blur = min(blur_score / 500.0, 1.0) * 70  # 최대 70점

    mean_brightness = img.mean()
    # 너무 어둡거나 너무 밝으면 감점
    brightness_score = max(0, 30 - abs(mean_brightness - 128) / 128 * 30)

    return round(normalized_blur + brightness_score, 1)


def preprocess_image(image_path: Path) -> Path:
    """
    이미지 전처리: 기울기 보정 + 대비 향상 + 리사이즈.
    처리된 이미지를 같은 폴더에 _processed 접미사로 저장 후 경로 반환.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        logger.warning("이미지 로드 실패: %s", image_path)
        return image_path

    img = _deskew(img)
    img = _enhance_contrast(img)
    img = _resize_if_needed(img)

    out_path = image_path.parent / (image_path.stem + "_processed" + image_path.suffix)
    cv2.imwrite(str(out_path), img)
    return out_path


def pdf_to_images(pdf_path: Path) -> list[Path]:
    """PDF 각 페이지를 PNG로 변환해서 경로 목록 반환."""
    doc = fitz.open(str(pdf_path))
    output_paths = []

    for i, page in enumerate(doc):
        mat = fitz.Matrix(2.0, 2.0)  # 2x 해상도
        pix = page.get_pixmap(matrix=mat)
        out_path = pdf_path.parent / f"{pdf_path.stem}_page{i+1}.png"
        pix.save(str(out_path))
        output_paths.append(out_path)

    doc.close()
    logger.info("PDF %s → %d 페이지 변환", pdf_path.name, len(output_paths))
    return output_paths


def to_base64(image_path: Path) -> tuple[str, str]:
    """
    이미지를 base64로 인코딩.
    Returns (base64_string, media_type).
    """
    suffix = image_path.suffix.lower()
    media_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_type_map.get(suffix, "image/jpeg")

    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")

    return data, media_type


def prepare_files_for_grading(file_paths: list[Path]) -> list[tuple[Path, float]]:
    """
    파일 목록을 받아 전처리 후 (처리된_경로, 품질점수) 목록 반환.
    PDF는 페이지별로 분리.
    """
    result = []
    for path in file_paths:
        if path.suffix.lower() == ".pdf":
            pages = pdf_to_images(path)
            for page_path in pages:
                processed = preprocess_image(page_path)
                score = compute_quality_score(processed)
                result.append((processed, score))
        else:
            processed = preprocess_image(path)
            score = compute_quality_score(processed)
            result.append((processed, score))
    return result


# ─── 내부 헬퍼 ──────────────────────────────────────────────

def _deskew(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 5:
        return img
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    if abs(angle) < 0.5:  # 보정 불필요
        return img
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _enhance_contrast(img: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def _resize_if_needed(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    if max(h, w) <= MAX_IMAGE_DIMENSION:
        return img
    scale = MAX_IMAGE_DIMENSION / max(h, w)
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
