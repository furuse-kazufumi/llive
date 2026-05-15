"""KAR — Knowledge Autarky Roadmap.

manifest-driven ingestor + corpus catalog. Spec §A*3 Knowledge autarky の
operational support layer.
"""

from llive.kar.manifests import (
    CorpusManifest,
    list_manifests,
    main,
    total_size_gb,
)

__all__ = ["CorpusManifest", "list_manifests", "main", "total_size_gb"]
