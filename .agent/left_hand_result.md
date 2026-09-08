## 实测发现（与文档不同之处）

1. **`pretrained/canon_in_d_major1` 是双手 AdaptNet 策略，不是左手策略**（checkpoint 内含 `actor.meta1/meta2`）。文档建议的 `cfg/left_demo.py --ckpt pretrained/canon_in_d_major1` 会报 `ob_normalizer 416 vs 208` 尺寸错误（已实测）。`pretrained` 中没有左手单手策略，必须用 `cfg/two_demo.py`，录制时同时得到 LH 16 + RH 16 共 32 个节点。
2. **无头 segfault 的根因是 `create_sim` 初始化图形上下文**。按文档第七节预案改用 `graphics_device=-1` 后彻底解决（Tesla T4 无显示输出，机器无 Vulkan）。

## 代码修改

`main.py`：
- 新增 `--headless`（跳过 `env.render()`）、`--graphics-device`（headless 时默认 `-1`）、`--record`（默认 `recordings/left_hand_motion.json`）、`--max-steps`（headless 时默认 600）
- `test()` 改为固定步数循环，不再依赖 `request_quit`，保留原有精度统计
- `MotionRecorder`：按名称查找刚体（遍历 LH/RH 两个 actor），每帧保存世界坐标 position + xyzw quaternion，done 时打 `reset` 标记；初始化时打印全部刚体名供核对（实测 `LH:wrist`=39，确有 `wrist_dx/dy/dz` 辅助节点，名称查找无歧义）

新增工具：
- `tools/import_motion.py` — Blender 导入器：为每个节点建 Empty 并插入 location/rotation 关键帧，xyzw→wxyz 转换，z-up 直通，reset 帧警告
- `tools/verify_recording.py` — 录制文件校验
- `tools/test_import_motion_mock.py` — 无 Blender 时的导入逻辑测试（已通过）

## 验证结果

`recordings/left_hand_motion.json`（3.7 MB）：600 帧 @ 60fps = 10 秒，32 节点，无 reset（动作连续），四元数全部单位化，逐帧最大跳变 ≤ 0.04 m（合理），位置范围在吉他颈部/指板附近。

## 使用命令

Isaac Gym 无头录制：
```bash
python main.py cfg/two_demo.py \
  --ckpt pretrained/canon_in_d_major1 \
  --note assets/notes/canon_in_d_major1.json \
  --test --headless --device 0            # 默认录 600 帧
# 加长录制: --max-steps 2400 (40秒), 自定义路径: --record recordings/foo.json
```

Blender 侧导入：
```bash
blender --background --python tools/import_motion.py -- recordings/left_hand_motion.json
```
播放检查无跳变后，即可进行网格与角色重定向。若后续自己训练了左手单手策略，用 `cfg/left_demo.py --ckpt <左手ckpt>` 同样可直接录制（节点列表自动从配置读取）。