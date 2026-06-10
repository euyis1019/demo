# 素材来源与许可（CREDITS）

| 资源 | 文件 | 作者/来源 | 许可 |
|---|---|---|---|
| 村庄 tileset / 角色 / 头像 | `assets/gfx/na/*` | Pixel-boy (Anokolisa)，[Ninja Adventure Asset Pack](https://github.com/pixel-boy/NinjaAdventure)（镜像：[superpowers-asset-packs](https://github.com/sparklinlabs/superpowers-asset-packs)） | **CC0**（公有领域，可商用，无需署名） |
| 背景音乐 | `assets/audio/theme_village.ogg` | 同上（Ninja Adventure musics/theme-1） | **CC0** |
| 脚步声 / 提示音 | `assets/audio/{footstep,notify}.wav` | 本项目程序合成（Python wave） | CC0 等同（自制） |

角色帧布局：16×16/帧，4 列走帧 × 前 4 行方向（行0=下/1=右/2=上/3=左）。
角色分配：char_5=玩家（草帽农夫）、char_9=老钱（白须老者）、
char_12=阿香（黑发红衣）、char_2=大山（橙衣壮汉）；face_N 为对应头像。
地面/物件 tile 坐标见 scripts/config.gd（NA_* 常量，逐块目检+截图迭代核定）。
