"""Shared file-discovery helpers."""
import os
from typing import List


def find_pdfs(root_dir: str) -> List[str]:
    """Recursively find every .pdf under root_dir, sorted for stable ordering.

    Syllabus/book collections are commonly organized in nested per-department
    or per-university folders (e.g. "syllabi/B002 AU Syllabus/AU UG/AU R2021
    CSE/B.E.CSE (1).pdf") rather than dropped flat into one directory, so a
    plain os.listdir() misses most of them.
    """
    paths = []
    for dirpath, _dirnames, filenames in os.walk(root_dir):
        for f in filenames:
            if f.lower().endswith(".pdf"):
                paths.append(os.path.join(dirpath, f))
    return sorted(paths)
