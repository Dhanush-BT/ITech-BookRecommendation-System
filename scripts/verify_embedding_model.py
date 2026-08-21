"""Step-0 gate: confirm the embedding model actually loads and encodes on this machine
before any pipeline code is written to depend on it."""
import time

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def resolve_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def main() -> None:
    device = resolve_device()
    print(f"torch: {torch.__version__}, resolved device: {device}")

    t0 = time.time()
    model = SentenceTransformer(MODEL_NAME, device=device)
    print(f"Loaded {MODEL_NAME} in {time.time() - t0:.1f}s")
    print(f"max_seq_length: {model.max_seq_length}")

    query = QUERY_PREFIX + "gear trains and their applications"
    passage = (
        "Gear Trains. A gear train is a mechanism formed by mounting gears on a frame so "
        "that the teeth of the gears engage. Gear teeth are designed to ensure the pitch "
        "circles of engaging gears roll without slipping, producing a smooth transmission "
        "of rotation from one gear to the next."
    )

    t0 = time.time()
    q_vec = model.encode(query, normalize_embeddings=True)
    p_vec = model.encode(passage, normalize_embeddings=True)
    elapsed = time.time() - t0

    print(f"query vector shape: {q_vec.shape}, dtype: {q_vec.dtype}")
    print(f"passage vector shape: {p_vec.shape}, dtype: {p_vec.dtype}")
    print(f"encode time for 2 short strings: {elapsed:.3f}s")

    sim_related = float(np.dot(q_vec, p_vec))
    unrelated_passage = (
        "Professional English communication skills involve reading, writing, and "
        "presenting complex texts, summaries, articles, and essays effectively."
    )
    u_vec = model.encode(unrelated_passage, normalize_embeddings=True)
    sim_unrelated = float(np.dot(q_vec, u_vec))

    print(f"cosine(query, related passage)   = {sim_related:.4f}")
    print(f"cosine(query, unrelated passage) = {sim_unrelated:.4f}")

    assert sim_related > sim_unrelated, (
        "Sanity check failed: related passage should score higher than unrelated one"
    )
    print("PASS: related passage scores higher than unrelated passage.")

    t0 = time.time()
    batch = [passage] * 32
    _ = model.encode(batch, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
    print(f"batch encode 32 passages: {time.time() - t0:.3f}s")

    print("\nSTEP 0 GATE: PASS")


if __name__ == "__main__":
    main()
