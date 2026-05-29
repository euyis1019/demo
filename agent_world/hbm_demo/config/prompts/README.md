# Agent Prompt 配置索引

本目录集中管理 Demo 中影响 Agent 行为与 Prompt 注入的 YAML 配置。

| 路径 | 用途 | 加载方 |
|------|------|--------|
| `abcs/turn_control.yaml` | ABCS 开关、world loop、prompt trace | F07 `config.py` |
| `abcs/story_knowledge/` | Phase 知识、Agent overlay、Turn hints | F07 `knowledge.py` |
| `routing/routing.yaml` | agent_driven 路由信号 | F05 `routing_config.py` |
| `virtual_player/` | 虚拟玩家配置与 Phase 地点 | F17 |
| `../hbm_scenario.yaml`（仓库根） | Agent soul、场景 LLM | Runner seed |

路径解析：`shared/prompt_paths.py`
