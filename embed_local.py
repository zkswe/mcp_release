# -*- coding: utf-8 -*-
"""FlyThings_mcp_open 本地 embedding：内置 bge-small-zh ONNX 模型，完全离线向量化。

无需任何 API Key。模型文件在 models/bge-small-zh/（model_quantized.onnx + tokenizer.json）。
"""
import json, os, sys

_BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(_BASE, 'models', 'bge-small-zh')
MODEL_FILE = os.path.join(MODEL_DIR, 'model_quantized.onnx')
TOKENIZER_FILE = os.path.join(MODEL_DIR, 'tokenizer.json')

_session = None
_tokenizer = None


def available():
    """模型文件是否齐全。"""
    return os.path.isfile(MODEL_FILE) and os.path.isfile(TOKENIZER_FILE)


def _load():
    global _session, _tokenizer
    if _session is not None:
        return
    import onnxruntime as ort
    from tokenizers import Tokenizer
    _session = ort.InferenceSession(MODEL_FILE, providers=['CPUExecutionProvider'])
    _tokenizer = Tokenizer.from_file(TOKENIZER_FILE)
    _tokenizer.enable_truncation(max_length=512)  # bge-small-zh 最大序列 512


def embed(text):
    """文本 → 512 维向量（本地模型，离线）。"""
    _load()
    enc = _tokenizer.encode(text)
    import numpy as np
    ids = np.array([enc.ids], dtype=np.int64)
    mask = np.array([enc.attention_mask], dtype=np.int64)
    ttype = np.array([enc.type_ids], dtype=np.int64)
    out = _session.run(None, {'input_ids': ids, 'attention_mask': mask, 'token_type_ids': ttype})
    hidden = out[0][0]          # [seq_len, 512]
    vec = hidden[0]             # CLS token 作为句向量（bge 惯例）
    # 归一化（bge 模型输出已是句向量，保险起见再归一化一次）
    norm = float(np.sqrt((vec * vec).sum()))
    if norm > 0:
        vec = vec / norm
    return [float(x) for x in vec]


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    print('模型可用:', available())
    if available():
        v = embed('ZKListView adapter 数据绑定')
        print('向量维度:', len(v))
        print('前 5 维:', [round(x, 4) for x in v[:5]])
