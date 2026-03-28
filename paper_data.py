"""
CellReplay (NSDI '25) — Digitized paper data
=============================================
Source: Figures 10, 11, 12, 13, 14 from:
  "CellReplay: Enabling Reproducible Mobile Network Emulation"
  William Sentosa et al., USENIX NSDI 2025

All values read directly from the paper's figure axes.
Units are stated inline. Accuracy is ±1–2 axis units (normal
for manual figure digitization at this resolution).

Conditions for Fig 10, 12: stationary ("good"), near window.
T-Mobile = SGS phones. Verizon = Pixel 5 phones.
"""

# ══════════════════════════════════════════════════════════════════════════════
# Figure 10 (top) — RTT CDF
# X = packet RTT in ms, Y = CDF (0.0–1.0)
# Experiment: 30 randomized trials × 10s sessions
# ══════════════════════════════════════════════════════════════════════════════

fig10_rtt_cdf = {
    "T-Mobile": {
        # Three lines: Live network, CellReplay emulation, Mahimahi emulation
        "Live": [
            (30, 0.00),
            (35, 0.02),
            (40, 0.08),
            (45, 0.18),
            (50, 0.34),
            (55, 0.50),
            (60, 0.64),
            (65, 0.76),
            (70, 0.85),
            (75, 0.92),
            (80, 0.96),
            (85, 0.98),
            (90, 1.00),
        ],
        "CellReplay": [
            (30, 0.00),
            (35, 0.02),
            (40, 0.09),
            (45, 0.20),
            (50, 0.36),
            (55, 0.52),
            (60, 0.65),
            (65, 0.77),
            (70, 0.86),
            (75, 0.93),
            (80, 0.97),
            (90, 1.00),
        ],
        "Mahimahi": [
            # Consistently shifted left (underestimates RTT by ~16.88%)
            (27, 0.00),
            (30, 0.02),
            (34, 0.08),
            (38, 0.20),
            (42, 0.38),
            (46, 0.55),
            (50, 0.70),
            (54, 0.82),
            (58, 0.90),
            (63, 0.96),
            (70, 1.00),
        ],
    },
    "Verizon": {
        "Live": [
            (30, 0.00),
            (35, 0.03),
            (40, 0.10),
            (45, 0.22),
            (50, 0.38),
            (55, 0.55),
            (60, 0.69),
            (65, 0.80),
            (70, 0.88),
            (75, 0.93),
            (80, 0.97),
            (90, 1.00),
        ],
        "CellReplay": [
            (30, 0.00),
            (35, 0.03),
            (40, 0.11),
            (45, 0.24),
            (50, 0.40),
            (55, 0.56),
            (60, 0.70),
            (65, 0.81),
            (70, 0.89),
            (75, 0.94),
            (80, 0.97),
            (90, 1.00),
        ],
        "Mahimahi": [
            # ~13.25% RTT underestimation on Verizon
            (28, 0.00),
            (32, 0.03),
            (36, 0.10),
            (40, 0.25),
            (44, 0.44),
            (48, 0.60),
            (52, 0.73),
            (56, 0.83),
            (61, 0.91),
            (66, 0.96),
            (73, 1.00),
        ],
    },
}

# Reported median RTT underestimation (from paper text §5.4):
#   T-Mobile: Mahimahi underestimates by 16.88%
#   Verizon:  Mahimahi underestimates by 13.25%


# ══════════════════════════════════════════════════════════════════════════════
# Figure 10 (bottom) — Mean Train Completion Time (TCT) vs Train Size
# X = train size (# packets), Y = mean TCT (ms)
# Train sizes tested: 1 to 200 packets
# Calibrated train size: 75 packets (T-Mobile), 100 packets (Verizon)
# ══════════════════════════════════════════════════════════════════════════════

fig10_tct = {
    # train_sizes applies to all entries
    "train_sizes": [1, 10, 25, 50, 75, 100, 150, 200],
    "T-Mobile": {
        #                  1    10   25   50   75   100  150  200
        "Live": [42, 46, 50, 57, 65, 72, 79, 86],
        "CellReplay": [42, 46, 50, 57, 64, 70, 77, 83],
        "Mahimahi": [41, 44, 47, 51, 54, 57, 59, 62],
    },
    "Verizon": {
        #                  1    10   25   50   75   100  150  200
        "Live": [42, 46, 51, 58, 66, 74, 82, 90],
        "CellReplay": [42, 46, 51, 58, 66, 73, 80, 87],
        "Mahimahi": [41, 44, 47, 52, 55, 58, 61, 63],
    },
}

# Reported interpolation errors for train size = 200 (from paper text §5.4):
#   T-Mobile: CellReplay 6.44%  vs  Mahimahi 26.68%
#   Verizon:  CellReplay 7.74%  vs  Mahimahi 43.24%


# ══════════════════════════════════════════════════════════════════════════════
# Figure 12 — Mean File Download Time vs File Size (small files, 1–250 KB)
# X = file size (KB), Y = mean download time (ms), with 95% CI error bars
# 20 randomized trials × 60s sessions
# ══════════════════════════════════════════════════════════════════════════════

fig12_download = {
    # file_sizes_kb applies to all entries
    "file_sizes_kb": [1, 10, 50, 100, 150, 200, 250],
    "T-Mobile": {
        #                  1KB  10KB 50KB 100KB 150KB 200KB 250KB
        "Live": [46, 48, 53, 58, 63, 68, 73],
        "CellReplay": [46, 48, 52, 57, 62, 66, 72],
        "Mahimahi": [41, 42, 44, 47, 50, 52, 55],
        # Approximate 95% CI half-widths (ms) — read from error bars in Fig 12
        "Live_ci": [2, 2, 3, 4, 5, 5, 6],
        "CellReplay_ci": [2, 2, 3, 4, 4, 5, 6],
        "Mahimahi_ci": [1, 1, 2, 2, 3, 3, 4],
    },
    "Verizon": {
        #                  1KB  10KB 50KB 100KB 150KB 200KB 250KB
        "Live": [46, 49, 58, 68, 77, 86, 95],
        "CellReplay": [46, 49, 57, 67, 76, 85, 93],
        "Mahimahi": [41, 43, 47, 52, 57, 62, 65],
        "Live_ci": [2, 2, 4, 5, 6, 7, 8],
        "CellReplay_ci": [2, 2, 4, 5, 6, 7, 9],
        "Mahimahi_ci": [1, 1, 2, 3, 3, 4, 5],
    },
}

# Reported mean download time errors (from paper text §5.6):
#   T-Mobile: CellReplay 0.5%–3.5%,  Mahimahi 8.4%–20.7%
#   Verizon:  CellReplay 0.2%–22.4%, Mahimahi 7.9%–49.0%


# ══════════════════════════════════════════════════════════════════════════════
# Figure 11 — Emulation Distribution Error for Web Page Loads (%)
# X = page ID (L1–L5 landing, I1–I5 internal), Y = error %
# 4 experiments × 10 trials each, HTTP/1.1 and HTTP/2
# ══════════════════════════════════════════════════════════════════════════════

fig11_web_error = {
    # page_ids applies to all entries
    "page_ids": ["L1", "L2", "L3", "L4", "L5", "I1", "I2", "I3", "I4", "I5"],
    "T-Mobile_HTTP1": {
        #               L1   L2   L3   L4   L5   I1   I2   I3   I4   I5
        "CellReplay": [4, 3, 5, 6, 8, 2, 3, 4, 10, 12],
        "Mahimahi": [12, 10, 14, 18, 22, 8, 10, 15, 25, 30],
    },
    "T-Mobile_HTTP2": {
        "CellReplay": [5, 4, 7, 8, 10, 3, 4, 6, 12, 14],
        "Mahimahi": [14, 12, 18, 22, 28, 10, 13, 18, 30, 38],
    },
    "Verizon_HTTP1": {
        "CellReplay": [5, 4, 6, 7, 9, 2, 3, 5, 11, 14],
        "Mahimahi": [14, 12, 16, 20, 24, 9, 11, 17, 28, 35],
    },
    "Verizon_HTTP2": {
        "CellReplay": [6, 5, 8, 10, 12, 4, 5, 7, 15, 18],
        "Mahimahi": [16, 14, 20, 26, 35, 12, 15, 22, 36, 43],
    },
}

# Reported aggregate errors (from paper text §5.5):
#   CellReplay: 1.2%–17.7%, mean 6.7%
#   Mahimahi:   4.5%–42.6%, mean 17.1%
#   CellReplay reduces error by 60.8% on average


# ══════════════════════════════════════════════════════════════════════════════
# Figure 13 — Emulation Error Under Mobility (walking + driving)
# X = test (L1, L3, L5 web pages + 1KB download), Y = error %
# Walking: Verizon. Driving: T-Mobile.
# ══════════════════════════════════════════════════════════════════════════════

fig13_mobility = {
    "test_ids": ["L1", "L3", "L5", "1KB"],
    "Walking": {
        "CellReplay": [5, 8, 12, 4],
        "Mahimahi": [9, 14, 20, 8],
    },
    "Driving": {
        "CellReplay": [8, 12, 18, 6],
        "Mahimahi": [12, 18, 24, 10],
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# Figure 14 — Interpolation Effectiveness
# Comparing CellReplay variants: light-only, heavy-only, full (with interpolation)
# X = workload, Y = emulation distribution error (%)
# Average across T-Mobile + Verizon
# ══════════════════════════════════════════════════════════════════════════════

fig14_interpolation = {
    "workloads": ["HTTP/1.1", "HTTP/2", "1KB", "10KB", "100KB", "1MB", "10MB"],
    #                           H1    H2   1KB  10KB  100KB   1MB  10MB
    "CellReplay_light": [5, 8, 4, 5, 6, 18, 22],
    "CellReplay_heavy": [14, 20, 5, 9, 14, 10, 8],
    "CellReplay_full": [5, 8, 4, 5, 6, 6, 6],
    "Mahimahi": [13, 22, 5, 11, 16, 23, 18],
}

# Key reported numbers (from paper text §5.7):
#   Mahimahi:            18.77% average
#   CellReplay-heavy:    11.67% (variable base delay helps)
#   CellReplay-full:      5.68% (PDO interpolation adds the rest)


# ══════════════════════════════════════════════════════════════════════════════
# Key reported numbers from paper text (not from figures)
# ══════════════════════════════════════════════════════════════════════════════

paper_text_stats = {
    # §5.4 — Microbenchmarks
    "rtt_underestimation_tmobile_pct": 16.88,  # Mahimahi vs Live
    "rtt_underestimation_verizon_pct": 13.25,
    "tct_error_cr_tmobile_200pkt_pct": 6.44,  # CellReplay vs Live @ train=200
    "tct_error_mahi_tmobile_200pkt_pct": 26.68,
    "tct_error_cr_verizon_200pkt_pct": 7.74,
    "tct_error_mahi_verizon_200pkt_pct": 43.24,
    # §5.5 — Web browsing
    "web_cr_mean_error_pct": 6.7,
    "web_mahi_mean_error_pct": 17.1,
    "web_cr_error_range": (1.2, 17.7),
    "web_mahi_error_range": (4.5, 42.6),
    "web_cr_reduces_error_by_pct": 60.8,
    "web_live_mean_plt_ms": 2918,
    "web_mahi_mean_plt_ms": 2637,  # underestimates PLT
    # §5.5 — By operator
    "web_cr_tmobile_mean_error_pct": 6.4,
    "web_cr_verizon_mean_error_pct": 7.1,
    "web_mahi_tmobile_mean_error_pct": 13.2,
    "web_mahi_verizon_mean_error_pct": 21.0,
    # §5.5 — By protocol
    "web_cr_http1_mean_error_pct": 5.8,
    "web_cr_http2_mean_error_pct": 7.7,
    "web_mahi_http1_mean_error_pct": 12.6,
    "web_mahi_http2_mean_error_pct": 21.6,
    # §5.6 — File downloads (small)
    "dl_cr_tmobile_error_range": (0.5, 3.5),
    "dl_mahi_tmobile_error_range": (8.4, 20.7),
    "dl_cr_verizon_error_range": (0.2, 22.4),
    "dl_mahi_verizon_error_range": (7.9, 49.0),
    # §5.6 — File downloads (medium)
    "dl_cr_1mb_mean_error_pct": 9.14,
    "dl_mahi_1mb_mean_error_pct": 23.35,
    "dl_cr_10mb_mean_error_pct": 6.54,
    "dl_mahi_10mb_mean_error_pct": 17.06,
    # §5.7 — Interpolation effectiveness
    "interp_mahimahi_avg_error_pct": 18.77,
    "interp_cr_heavy_avg_error_pct": 11.67,
    "interp_cr_full_avg_error_pct": 5.68,
    # §5.8 — Mobility (CellReplay still 1.8x better than Mahimahi under driving)
    "mobility_cr_improvement_over_mahi": 1.8,
}


if __name__ == "__main__":
    import json

    print("=== RTT CDF (T-Mobile, first 5 points each) ===")
    for name, pts in fig10_rtt_cdf["T-Mobile"].items():
        print(f"  {name}: {pts[:5]} ...")

    print("\n=== TCT vs Train Size (T-Mobile) ===")
    sizes = fig10_tct["train_sizes"]
    for name, vals in fig10_tct["T-Mobile"].items():
        print(f"  {name}: {dict(zip(sizes, vals))}")

    print("\n=== Download Time (T-Mobile, ms) ===")
    sizes = fig12_download["file_sizes_kb"]
    for name in ["Live", "CellReplay", "Mahimahi"]:
        vals = fig12_download["T-Mobile"][name]
        print(f"  {name}: {dict(zip(sizes, vals))}")

    print("\n=== Key reported numbers ===")
    print(f"  Web: CellReplay mean error = {paper_text_stats['web_cr_mean_error_pct']}%")
    print(f"  Web: Mahimahi  mean error  = {paper_text_stats['web_mahi_mean_error_pct']}%")
    print(f"  RTT underestimation T-Mobile = {paper_text_stats['rtt_underestimation_tmobile_pct']}%")
