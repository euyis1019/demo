# 剧情模式素材（Story Mode Assets）

生成完成后把图片放进对应子目录。Vite 访问路径：`/assets/story/...`

## places/ — 场景背景（16:9，建议 1920×1080 或 2560×1440）

| 文件名 | 地点 |
|--------|------|
| `nvidia_reception_bg.webp` | 英伟达接待前台 |
| `jensen_private_room_bg.webp` | 黄仁勋私人会议室 |
| `negotiation_room_bg.webp` | HBM 主谈判室 |
| `openai_hq_bg.webp` | OpenAI 总部 |

也支持 `.png` / `.jpg`，实现阶段会按上表 basename 读取。

## avatars/ — 剧情模式字幕区头像（透明 PNG，1:1）

| 文件名 | agent_id |
|--------|----------|
| `agent_1.png` | 1 |
| `agent_2.png` | 2 |
| `agent_3.png` | 3 |
| `agent_4.png` | 4 |
| `agent_5.png` | 5 |
| `agent_6.png` | 6 |
| `agent_7.png` | 7 |
| `player.png` | 玩家 |

更换绿幕原图时：将新图暂存为 `agent_N.webp`，运行 `web/scripts/process_story_avatars.py` 生成 PNG 后删除 webp。
