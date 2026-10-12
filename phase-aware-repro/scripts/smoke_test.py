#!/usr/bin/env python3
"""Smoke test: short baseline MAPPO run to verify the pipeline and measure speed."""
from copy import deepcopy
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).parent / "src"))
from experiment_core import BASE_CFG, train_single_run

cfg = deepcopy(BASE_CFG)
cfg["episodes"] = 40
cfg["controller_type"] = "baseline"
cfg["results_dir"] = "smoke_results"
cfg["device"] = "cpu"

start = time.time()
results = train_single_run("baseline", 21, cfg, Path("smoke_results"))
elapsed = time.time() - start
print(f"\nSmoke run finished in {elapsed:.1f}s "
      f"({elapsed / cfg['episodes']:.2f}s/episode)")
print(f"final metrics: success={results['final_success_rate']:.1f}% "
      f"acq={results['final_acquisition_rate']:.1f}% "
      f"error={results['final_position_error']:.2f}m")
