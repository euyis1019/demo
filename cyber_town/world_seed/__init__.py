"""世界种子层：scenario.yaml 的读取与灌库（纯数据，不含业务逻辑）。"""

from cyber_town.world_seed.loader import load_scenario, seed_into_db

__all__ = ["load_scenario", "seed_into_db"]
