---
name: manga-ocr
description: |
  漫画画像から日本語テキストを OCR で抽出する skill。
  v0.G HumorKB の MNG-02 (speech bubble / narration / SFX 分離 + OCR) の
  実装エントリポイント. 上流 (kha-white/manga-ocr, Apache-2.0, 商用可) の
  ラッパー. 縦書き / 横書き / ふりがな / 複数行に対応.
  Auto-trigger when: ユーザーが「漫画 OCR」「manga ocr」「吹き出し読み取り」
  「セリフ抽出」「manga-ocr の使い方」を発話、または v0.G MNG-02 配線で
  speech bubble 内テキスト抽出が surface したとき.
---

# manga-ocr — 漫画画像から日本語テキストを OCR

## 何を解く skill か

漫画特有の **縦書き + ふりがな + 手書き風フォント + 重ね効果** に対応した OCR.
汎用 OCR (Tesseract jpn) では精度不足のため、kha-white/manga-ocr (HuggingFace
日本語漫画特化 fine-tuned ViT + GPT2) を使う.

llive v0.G ([[../docs/requirements_v0.G_manga_reading_humor.md]]) の柱 A-2
「Speech Bubble / Narration / SFX 分離 + OCR」を実装する.

## 上流情報

- **Repo**: `https://github.com/kha-white/manga-ocr`
- **License**: Apache-2.0 (商用 OK, llive Apache-2.0 + Commercial dual と整合)
- **依存**: `pip install manga-ocr` (PyTorch + transformers が暗黙依存)
- **GPU**: optional. CPU でも数秒 / 画像で動作
- **Model**: HuggingFace Hub `kha-white/manga-ocr-base` (約 440 MB) を初回 DL

## インストール

```powershell
# Python 3.11 を前提 (llive 標準, project_python_311_unification.md)
py -3.11 -m pip install manga-ocr
```

`llive` 本体 `pyproject.toml` には `[manga]` optional extra として追加する
(重い依存なので default install には含めない):

```toml
[project.optional-dependencies]
manga = ["manga-ocr>=0.1.10"]
```

## 使い方 (最小サンプル)

### A. 単一画像 → 文字列

```python
from manga_ocr import MangaOcr

ocr = MangaOcr()  # 初回 DL あり, 以降キャッシュ
text = ocr("path/to/bubble.png")
print(text)
```

### B. PIL Image (in-memory)

```python
from PIL import Image
from manga_ocr import MangaOcr

ocr = MangaOcr()
img = Image.open("page.png").crop((x0, y0, x1, y1))  # 吹き出し領域だけ切出し
text = ocr(img)
```

### C. llive 統合 (MNG-02 接続点)

`src/llive/multimodal/manga/ocr_bridge.py` (新規) として
`MangaOcrAdapter` を実装する想定:

```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class OcrResult:
    raw_text: str
    bbox: tuple[int, int, int, int]
    confidence: float | None = None  # manga-ocr は提供しない. None で埋める
    error: Optional[str] = None      # silently drop しない

class MangaOcrAdapter:
    def __init__(self) -> None:
        from manga_ocr import MangaOcr   # lazy import (optional dep)
        self._ocr = MangaOcr()

    def transcribe(self, image, bbox: tuple[int, int, int, int]) -> OcrResult:
        try:
            crop = image.crop(bbox)
            text = self._ocr(crop)
            return OcrResult(raw_text=text, bbox=bbox)
        except Exception as exc:  # noqa: BLE001 (boundary)
            return OcrResult(raw_text="", bbox=bbox, error=str(exc))
```

## 制約と honest disclosure

| 項目 | 状態 | メモ |
|---|---|---|
| ライセンス | ✅ Apache-2.0 | llive と商用整合 |
| 縦書き | ✅ | 漫画は基本縦書き対応 |
| ふりがな | ✅ | 自動処理 |
| 手書き SFX | ⚠️ 部分対応 | フォント次第で精度低下 |
| 信頼度スコア | ❌ 提供されない | OcrResult.confidence=None |
| panel detection | ❌ 対応外 | 別途 MNG-01 で comic-text-detector or Magi (academic) を検討 |
| speaker attribution | ❌ 対応外 | 別 skill (MNG-03 geometry-based) で実装 |
| 初回 DL | 約 440MB | offline 環境では事前 cache |

## panel detector 候補 (MNG-01 で別途検討)

| 候補 | License | 商用 | メモ |
|---|---|---|---|
| Magi (ragavsachdeva) | academic only | ❌ | 学術研究のみ、llive Apache 商用と不整合 |
| comic-text-detector (dmMaze) | 要確認 | ? | 次セッションで確認 |
| mokuro (kha-white) | 要確認 | ? | OCR ベース、panel detection は限定的 |
| 自作 + OpenCV | OSS | ✅ | 罫線検出ベース、精度は劣るが license clear |

→ MNG-01 は **panel detector の OSS 棚卸し** を先にする (本 skill MNG-02 は OCR のみ).

## 連動

- `[[../docs/requirements_v0.G_manga_reading_humor.md]]` — v0.G 要件本体
- `[[../docs/requirements_v0.G_manga_reading_humor.md#柱 A: 漫画特化 panel reader]]`
- `[[../../memory/project_llive_manga_humor.md]]` — memory side
- `[[../../memory/feedback_skill_proactive_expansion.md]]` — skill 自律追加方針

## 使ったとき

- 必ず HumorKB に **構造のみ** 投入 (台詞コピー禁止, 柱 C-1 規律)
- 著作権ありの作品をスキャンする場合は **ユーザー所有物** に限定
- 公式公開素材 (e.g. `https://youngjump.jp/info/bazue/`) は引用ガイドライン内で使用可
