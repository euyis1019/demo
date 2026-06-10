"""管理类 agent（W5）：运行期的「世界幕后人员」。

铁律（方案 §4.8/§15）：管理 agent **只调配资源与感知输入，永不产生/修改
NPC 行为**——它们的输出要么是「思考预算分配」（激活策略），要么是
「世界事实」（环境事件），NPC 如何反应仍 100% 自主。

- ``activation_director``  激活导演：低频 LLM 元决策谁高频思考/谁休眠
- ``world_director``       世界事件导演：定期向世界投放环境事件
"""

from cyber_town.backend.directors.activation_director import ActivationDirector
from cyber_town.backend.directors.world_director import WorldDirector

__all__ = ["ActivationDirector", "WorldDirector"]
