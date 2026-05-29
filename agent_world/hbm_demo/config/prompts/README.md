# L0 — Prompt / 路由 / 虚拟玩家配置 (`config/prompts/`)

Demo 的**外置 Prompt 与剧情配置**。改 Agent 行为/剧情**只动这里**（与各 Feature 的
`config.py` 加载器），勿把 YAML 放回 `features/` 根目录。路径由 `shared/prompt_paths.py`
统一解析，索引见 `config/manifest.yaml`。

```text
config/
├── manifest.yaml                       # 所有 prompt 文件的路径索引（version + paths）
└── prompts/
    ├── abcs/                           # F07 Agent 行为控制（ABCS）
    │   ├── turn_control.yaml           #   选角(primary/passive/frozen)、world loop、
    │   │                               #   inject 窗口、各 Phase llm_params(温度/max_tokens)
    │   └── story_knowledge/            #   L4 故事知识
    │       ├── agents/agent_{1..7}.yaml#     每个 Agent 的 identity/speech_style/player_stance/
    │       │                           #     relationships + 各 Phase role_goal/example/checklist
    │       ├── shared/phase_{1..4}.yaml#     各幕共享背景
    │       ├── shared/plain_language.yaml #  「说人话」风格约束
    │       └── turn_hints.yaml         #     回合提示
    ├── routing/
    │   └── routing.yaml                # F05：mode(agent_driven)、各节点关键词
    │                                   # (approve/reject/expel/escort/return/phase4_deal)、
    │                                   # story_advance.enabled、Phase1 超时阈值
    └── virtual_player/
        ├── config.yaml                 # F17：enabled、player_agent_id(=0)
        └── phase_places.yaml           # F17：各 Phase 玩家(agent 0)所在房间
```

## 各 Agent 编号

`agents/agent_N.yaml` 对应 `hbm_scenario.yaml` 的 agent_id：
1=接待前台 · 2=Jensen Hwang · 3=Tech VP · 4=SK Hynix CEO · 5=Micron CEO ·
6=Samsung CEO · 7=Sam Altman。（玩家=agent 0，由 F17 虚拟玩家管理，无 prompt。）

## 加载关系

| 配置 | 加载器 |
|------|--------|
| `hbm_scenario.yaml`（demo 根） | `shared/config_loader.load_scenario` |
| `abcs/turn_control.yaml` | `features/f07_agent_control/config.py` |
| `abcs/story_knowledge/*` | `features/f07_agent_control/knowledge.py` |
| `routing/routing.yaml` | `features/f05_story_routing/routing_config.py` |
| `virtual_player/*` | `features/f17_virtual_player/config.py` · `player_entity.py` |

路径全部经 `shared/prompt_paths.py` 解析，便于整体迁移。
