"""story_studio — 设计期 Story Pack 生成工具（离线，dev_logs/45）。

定位：把一份 story brief 编译成整包 Story Pack（config/stories/<id>/）的离线 CLI。
是「编译器」，运行期解释器是「虚拟机」。**绝不进 Flask/Runner、绝不写 sim/**（safety 红线）。

公共出口（G1 契约 + 骨架）：
  - validate_brief / BRIEF_SCHEMA —— 用户输入契约
  - DESIGNER_OUTPUT_SCHEMA / validate_against —— 生成期中间产物契约
  - call_json_with_schema / LLMClient / StoryStudioError —— 管理 agent 基类（LLM 注入）
  - compile_pack / designer_output_to_story_graph —— 编排器骨架（落盘 + validate）
  - write_story_pack / assert_safe_target —— 落盘 + 安全红线
"""

from __future__ import annotations

from agent_world.hbm_demo.tools.story_studio.authoring_schemas import (
    DESIGNER_OUTPUT_SCHEMA,
    validate_against,
)
from agent_world.hbm_demo.tools.story_studio.base_agent import (
    LLMClient,
    StoryStudioError,
    call_json_with_schema,
)
from agent_world.hbm_demo.tools.story_studio.brief_schema import BRIEF_SCHEMA, validate_brief
from agent_world.hbm_demo.tools.story_studio.metering import (
    BudgetExceededError,
    GenerationTrace,
    metering_client,
)
from agent_world.hbm_demo.tools.story_studio.agents import Casting, Designer, Writer
from agent_world.hbm_demo.tools.story_studio.orchestrator import (
    CompileResult,
    assemble_full_sections,
    assemble_sections,
    brief_to_meta,
    compile_pack,
    designer_output_to_story_graph,
    generate,
    generate_full,
    regenerate_writer,
)
from agent_world.hbm_demo.tools.story_studio.asset_manifest import (
    render_asset_manifest,
    write_asset_manifest,
)
from agent_world.hbm_demo.tools.story_studio.review import render_review
from agent_world.hbm_demo.tools.story_studio.safety import (
    StoryStudioSafetyError,
    assert_safe_target,
)
from agent_world.hbm_demo.tools.story_studio.writer import write_story_pack

__all__ = [
    "BRIEF_SCHEMA",
    "validate_brief",
    "DESIGNER_OUTPUT_SCHEMA",
    "validate_against",
    "call_json_with_schema",
    "LLMClient",
    "StoryStudioError",
    "compile_pack",
    "CompileResult",
    "designer_output_to_story_graph",
    "brief_to_meta",
    "generate",
    "generate_full",
    "regenerate_writer",
    "assemble_full_sections",
    "assemble_sections",
    "render_review",
    "render_asset_manifest",
    "write_asset_manifest",
    "GenerationTrace",
    "BudgetExceededError",
    "metering_client",
    "Designer",
    "Casting",
    "Writer",
    "write_story_pack",
    "assert_safe_target",
    "StoryStudioSafetyError",
]
