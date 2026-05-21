"""Shared helpers for the Vedix corpus-preparation pipeline (§5.3.1).

Each stage of ``scripts/prepare_corpus.py`` is implemented as a sibling
module:

  1. ``acquisition``         — harvest paper candidates via MCPs
  2. ``download``            — stream PDF/XML/HTML payloads
  3. ``extraction``          — extract text from each format
  4. ``lang_verify``         — fasttext language ID + filter
  5. ``segmentation``        — spaCy paragraph split
  6. ``dedup``               — MinHashLSH near-duplicate removal
  7. ``labeling``            — rule-based positive labeling
  8. ``negative_generator``  — adversarial AI-style negatives via BYOK
  9. ``splits``              — stratified paper-level train/val/test
 10. ``stats``               — corpus_stats.json
"""

__all__ = []
