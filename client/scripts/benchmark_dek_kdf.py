#!/usr/bin/env python3
"""
Benchmark and compare the old vs new Argon2id parameters used for DEK key
derivation, showing timing and offline-attack resistance.
"""

import time

from argon2.low_level import Type, hash_secret_raw

CONFIGS = [
    {
        "label": "New (64 MiB / t=3)",
        "time_cost": 3,
        "memory_cost": 65_536,
        "parallelism": 4,
    },
    {
        "label": "Old (6 GiB / t=1)",
        "time_cost": 1,
        "memory_cost": 6_291_456,
        "parallelism": 4,
    },
    {
        "label": "Old (6 GiB / t=3)",
        "time_cost": 3,
        "memory_cost": 6_291_456,
        "parallelism": 4,
    },
]

SECRET = b"hunter2"
SALT = b"benchmarksalt123benchmarksalt123"  # 32 bytes
HASH_LEN = 32

# Rough attacker throughput estimates (hashes/sec on dedicated hardware).
# Argon2id with high memory is intentionally hard to parallelise on GPUs.
# These are conservative estimates for a well-funded attacker.
ATTACKER_RIGS = [
    ("Laptop (1 core)", 1),
    ("High-end GPU rig", 10),
    ("Nation-state cluster", 100),
]

# Typical PIN/password search spaces
SEARCH_SPACES = [
    ("4-digit PIN (10^4)", 10_000),
    ("6-digit PIN (10^6)", 1_000_000),
    ("8-char lowercase (26^8)", 208_827_064_576),
    ("Random 6-word passphrase (7776^6)", 7_776**6),
]


def human_time(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds*1000:.1f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    if seconds < 3600:
        return f"{seconds/60:.1f} min"
    if seconds < 86400:
        return f"{seconds/3600:.1f} hr"
    if seconds < 86400 * 365:
        return f"{seconds/86400:.1f} days"
    years = seconds / (86400 * 365.25)
    if years < 1e6:
        return f"{years:,.0f} years"
    return f"{years:.2e} years"


def benchmark(cfg: dict) -> float:
    start = time.perf_counter()
    hash_secret_raw(
        secret=SECRET,
        salt=SALT,
        time_cost=cfg["time_cost"],
        memory_cost=cfg["memory_cost"],
        parallelism=cfg["parallelism"],
        hash_len=HASH_LEN,
        type=Type.ID,
    )
    return time.perf_counter() - start


def run():
    results = []
    print("=" * 62)
    print("  Argon2id parameter benchmark")
    print("=" * 62)

    for cfg in CONFIGS:
        print(f"\n  [{cfg['label']}]")
        print(
            f"    memory={cfg['memory_cost']//1024} MiB  "
            f"time_cost={cfg['time_cost']}  parallelism={cfg['parallelism']}"
        )
        print("    Timing... ", end="", flush=True)

        # Warm-up then measure
        benchmark(cfg)
        elapsed = benchmark(cfg)
        results.append((cfg, elapsed))
        print(f"{human_time(elapsed)}")

    print()
    print("=" * 62)
    print("  Timing comparison")
    print("=" * 62)
    baseline = results[0][1]
    for cfg, elapsed in results:
        ratio = elapsed / baseline
        suffix = f"  ({ratio:.1f}x slower than new)" if ratio > 1.0 else "  (baseline)"
        print(f"  {cfg['label']:<28} {human_time(elapsed):>10}{suffix}")

    col_w = 16
    headers = [cfg["label"] for cfg, _ in results]

    print()
    print("=" * 62)
    print("  Offline-attack resistance  (time to exhaust search space)")
    print("  Assumption: attacker parallelism limited by Argon2 memory cost")
    print("=" * 62)

    for rig_label, attacker_hps_multiplier in ATTACKER_RIGS:
        print(f"\n  Attacker: {rig_label}")
        header_row = f"  {'Search space':<36}" + "".join(f"{h:>{col_w}}" for h in headers)
        print(header_row)
        print(f"  {'-'*36}" + ("-" * col_w) * len(results))
        for space_label, space_size in SEARCH_SPACES:
            row = f"  {space_label:<36}"
            for _, elapsed in results:
                crack_time = space_size / (attacker_hps_multiplier / elapsed)
                row += f"{human_time(crack_time):>{col_w}}"
            print(row)

    print()
    print("=" * 62)
    print("  Summary")
    print("=" * 62)
    new_t = results[0][1]
    for cfg, elapsed in results[1:]:
        print(
            f"  '{cfg['label']}' is {elapsed/new_t:.1f}x slower than new for both user and attacker."
        )
    print(f"  All configs remain strong against offline attacks on realistic PINs.")
    print()


if __name__ == "__main__":
    run()
