"""KAR ingest manifest catalog (library version).

scripts/import_rad_extended.py の thin wrapper として動く。実装は library に
寄せて importlib.util 経由のテストや、他モジュールからの直接利用を可能にする。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from typing import Literal


Phase = Literal["short", "mid", "long"]


@dataclass(frozen=True)
class CorpusManifest:
    name: str
    phase: Phase
    description: str
    license: str
    fetch_method: str
    estimated_size_gb: float
    requires_credentials: bool = False


_MANIFESTS: list[CorpusManifest] = [
    # 短期 (2026)
    CorpusManifest(
        name="arxiv_tier1",
        phase="short",
        description="cs.AI / cs.CL / physics.* / q-bio.* の full-text bulk",
        license="arXiv Bulk Data License",
        fetch_method="S3 bulk + arxiv-public-datasets",
        estimated_size_gb=120.0,
    ),
    CorpusManifest(
        name="wikipedia_multilang_10",
        phase="short",
        description="ja/en/zh/ko + de/fr/es/ru/ar/hi wiki dumps",
        license="CC BY-SA 3.0",
        fetch_method="https://dumps.wikimedia.org",
        estimated_size_gb=80.0,
    ),
    CorpusManifest(
        name="hacker_corpus_normalised",
        phase="short",
        description="既存 hacker_corpus を corpus2skill v2 階層化済みに正規化",
        license="various",
        fetch_method="local D:/docs/hacker_corpus + corpus2skill",
        estimated_size_gb=2.0,
    ),
    # 中期 (2027-2029)
    CorpusManifest(
        name="arxiv_full",
        phase="mid",
        description="arXiv 全領域 full-text",
        license="arXiv Bulk Data License",
        fetch_method="S3 bulk + diff sync",
        estimated_size_gb=500.0,
    ),
    CorpusManifest(
        name="pubmed_central",
        phase="mid",
        description="PubMed Central full-text",
        license="various (NIH-deposited)",
        fetch_method="NCBI bulk download",
        estimated_size_gb=100.0,
    ),
    CorpusManifest(
        name="gutenberg_ia_cc0",
        phase="mid",
        description="Project Gutenberg + Internet Archive CC0 古典",
        license="Public Domain / CC0",
        fetch_method="HTTP archive",
        estimated_size_gb=50.0,
    ),
    CorpusManifest(
        name="patents_uspto_jpo",
        phase="mid",
        description="USPTO + JPO 公開特許 full-text",
        license="public",
        fetch_method="USPTO bulk + J-PlatPat",
        estimated_size_gb=200.0,
    ),
    # 長期 (2030+)
    CorpusManifest(
        name="specialised_books_licensed",
        phase="long",
        description="専門書ライセンス済取り込み",
        license="vendor-agreement",
        fetch_method="vendor API",
        estimated_size_gb=300.0,
        requires_credentials=True,
    ),
    CorpusManifest(
        name="phd_dissertations_etd",
        phase="long",
        description="博士論文全文 (ETD ハーベスト)",
        license="institutional",
        fetch_method="ETD OAI-PMH",
        estimated_size_gb=400.0,
    ),
    CorpusManifest(
        name="endangered_languages",
        phase="long",
        description="絶滅言語コーパス",
        license="community-agreed",
        fetch_method="ELP API + partner archives",
        estimated_size_gb=20.0,
    ),
    CorpusManifest(
        name="multimodal_cc0",
        phase="long",
        description="CC0 写真・音声・動画 multi-modal",
        license="CC0",
        fetch_method="Wikimedia Commons + LAION-cc0",
        estimated_size_gb=2000.0,
    ),
]


def list_manifests(phase: Phase | None = None) -> list[CorpusManifest]:
    if phase is None:
        return list(_MANIFESTS)
    return [m for m in _MANIFESTS if m.phase == phase]


def total_size_gb(phase: Phase | None = None) -> float:
    return sum(m.estimated_size_gb for m in list_manifests(phase))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="import_rad_extended",
        description="KAR ingest manifest driver.",
    )
    p.add_argument("--list", action="store_true")
    p.add_argument("--plan", choices=["short", "mid", "long"])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--summary", action="store_true")
    args = p.parse_args(argv)

    if args.summary:
        print(
            json.dumps(
                {
                    "short_gb": total_size_gb("short"),
                    "mid_gb": total_size_gb("mid"),
                    "long_gb": total_size_gb("long"),
                    "total_gb": total_size_gb(None),
                },
                indent=2,
            )
        )
        return 0
    if args.list:
        out = [asdict(m) for m in list_manifests()]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if args.plan:
        manifests = list_manifests(args.plan)
        print(json.dumps([asdict(m) for m in manifests], ensure_ascii=False, indent=2))
        if args.dry_run:
            total = sum(m.estimated_size_gb for m in manifests)
            print(
                f"[dry-run] {args.plan} phase: {len(manifests)} manifests, ~{total:.1f} GB",
                file=sys.stderr,
            )
        return 0
    p.print_help()
    return 0


__all__ = [
    "CorpusManifest",
    "list_manifests",
    "main",
    "total_size_gb",
]
