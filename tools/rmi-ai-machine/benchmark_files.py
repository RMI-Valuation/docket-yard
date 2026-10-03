"""What the benchmark corpus's file names mean, said once.

`benchmark_sample.py` writes the sixty decisions' text as `<stratum>-<id>.txt` (`heavy-52526.txt`),
and every tool that reads the corpus back needs the decision id out of that name. Each used to
parse it its own way — `rsplit("-", 1)`, `split("-")[-1]`, a regex — which agree on every file
the sampler writes today and would each break differently on the first name that does not
(code review, 2026-08-30, `docs/deferred.md` § Benchmark scorer). One reader, so the
convention changes in one place.

Standard library only, and nothing from `docketyard`: `benchmark_run.py` runs on the operator's
GPU machine beside its siblings, and the scorers keep their distance from the code they score.
"""

from pathlib import Path


def decision_id_of(path: Path) -> str:
    """The decision id in a corpus file's name: `heavy-52526.txt` -> `52526`.

    The id is everything after the LAST hyphen of the stem, so a stratum that ever carries a
    hyphen of its own still yields the id, and a bare `52526.txt` (an OCR pass names its PDFs
    by id alone) yields itself."""
    return Path(path).stem.rsplit("-", 1)[-1]
