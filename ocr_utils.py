"""OCR 与图像 ROI 公共工具。

整合 launcher / water/recognizer / monthly_card / fishing.matcher 四处重复的:
  - 图像归一化降采样(norm1920)、归一化 ROI 切片(crop)
  - OCR 取拼接文本(ocr_text)、取"文字+中心坐标"列表(ocr_lines)
  - OCR 取"文字+置信度+中心坐标"明细(ocr_items)
  - 在 ROI 中查找关键字(find_text)

设计要点(为什么这么定签名):
  · `crop(frame, roi)` 是纯函数,roi=None 时直接返回原帧 —— 让 fishing 那种"自己已经
    crop 好了传子图"的调用方传 roi=None 即可,不必再绕一层。
  · `min_conf` 全部做成可选参数,默认 0.5(原 launcher/water/fishing 一致);月卡这种
    艺术字体场景调用时显式传 0.35。各家阈值不同 → 不用模块级常量,用参数传。
  · `ocr_lines` 返回 [(text, cx, cy)](归一化中心),`ocr_items` 返回更全的
    [(text, conf, (cx, cy))],分别对应"只要坐标"和"要按置信度筛选"两种用法。
    monthly_card 原来 items 带 conf,用它;launcher/water 不需要 conf,用 ocr_lines。
  · 所有函数失败不抛(OCR 是"尽力而为"),返回空串/空列表,失败原因写 dev_log。
"""
from __future__ import annotations

import cv2
import numpy as np

from capture import NORM_W
from fishing.matcher import _get_ocr
from runtime_guard import dev_log


def norm1920(frame: np.ndarray) -> np.ndarray:
    """宽 > NORM_W 时按比例降采样到 NORM_W(ROI/点击都用归一化分数,缩放不影响坐标),省 OCR 时间。"""
    h, w = frame.shape[:2]
    if w <= NORM_W:
        return frame
    nh = max(1, int(round(h * NORM_W / w)))
    return cv2.resize(frame, (NORM_W, nh), interpolation=cv2.INTER_AREA)


def crop(frame: np.ndarray, roi: tuple | None) -> np.ndarray:
    """按归一化 roi=(x0,y0,x1,y1) 切子图;roi=None 时原样返回(供已 crop 的调用方用)。"""
    if roi is None:
        return frame
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = roi
    return frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]


def _parse_items(raw, min_conf: float, frame_shape, roi):
    """把 RapidOCR 原始结果 → [(text, conf, box_center_in_full_frame_norm)]。
    box 中心按"整帧归一化"算(加上 roi 偏移),供 ocr_lines / ocr_items 共用。"""
    if not raw:
        return []
    fh, fw = frame_shape[:2]
    ox, oy = (roi[0] * fw, roi[1] * fh) if roi else (0.0, 0.0)
    out = []
    for it in raw:
        if it is None:
            continue
        try:
            box, txt, conf = it[0], str(it[1]).strip(), float(it[2])
        except (IndexError, ValueError, TypeError):
            continue
        if not txt or conf < min_conf:
            continue
        try:
            cx = (ox + sum(p[0] for p in box) / len(box)) / fw
            cy = (oy + sum(p[1] for p in box) / len(box)) / fh
        except (TypeError, ValueError, IndexError):
            cx = cy = 0.0
        out.append((txt, conf, (cx, cy)))
    return out


def ocr_text(frame: np.ndarray, roi: tuple | None = None, min_conf: float = 0.5) -> str:
    """OCR 指定 ROI(或整帧,roi=None)→ 拼接文本。
    fishing 调用方传"已 crop 的子图 + roi=None";launcher/water/monthly_card 传"整帧 + roi"。"""
    sub = crop(frame, roi)
    if sub is None or sub.size == 0:
        return ""
    try:
        res, _ = _get_ocr()(sub)
    except Exception as exc:
        dev_log("OCR 失败 roi=%r" % (roi,), exc)
        return ""
    items = _parse_items(res, min_conf, frame.shape, roi)
    return "".join(t[0] for t in items)


def ocr_lines(frame: np.ndarray, roi: tuple | None = None, min_conf: float = 0.5):
    """OCR → [(text, cx_norm, cy_norm), ...](文字框中心按整帧归一化)。"""
    sub = crop(frame, roi)
    if sub is None or sub.size == 0:
        return []
    try:
        res, _ = _get_ocr()(sub)
    except Exception as exc:
        dev_log("OCR 失败 roi=%r" % (roi,), exc)
        return []
    items = _parse_items(res, min_conf, frame.shape, roi)
    return [(t, c[0], c[1]) for t, _c, c in items]


def ocr_items(frame: np.ndarray, roi: tuple | None = None, min_conf: float = 0.5):
    """OCR → [(text, conf, (cx_norm, cy_norm)), ...]。
    比 ocr_lines 多返回置信度,供月卡等需要按 conf 二次筛选的场景。"""
    sub = crop(frame, roi)
    if sub is None or sub.size == 0:
        return []
    try:
        res, _ = _get_ocr()(sub)
    except Exception as exc:
        dev_log("OCR 失败 roi=%r" % (roi,), exc)
        return []
    return _parse_items(res, min_conf, frame.shape, roi)


def find_text(frame: np.ndarray, roi: tuple, keyword: str, min_conf: float = 0.5):
    """在 ROI 中 OCR 查找首个含 keyword 的文字框 → (cx_norm, cy_norm) 或 None。"""
    for txt, cx, cy in ocr_lines(frame, roi, min_conf):
        if keyword in txt:
            return (cx, cy)
    return None
