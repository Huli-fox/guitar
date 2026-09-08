下一步应录制 **Isaac Gym 中策略实际控制后的左手刚体姿态**，而不是录制策略输出的 action。

无头显卡完全可以完成：

- 物理仿真；
- 策略推理；
- 刚体状态读取；
- 动画数据保存；
- 后续导入 Blender。

不需要 viewer。你需要做的是让项目进入 **headless evaluation + fixed-frame recording** 模式。

---

## 一、先明确要录制什么

左手环境是：

```text
ICCGANLeftHand
```

配置在：

```text
cfg/left_demo.py
```

其中包含：

```python
character_model = "assets/left_hand_guitar.xml"
motion_file = "assets/motions/scale.json"
```

需要录制的节点是：

```text
LH:wrist

LH:thumb1
LH:thumb2
LH:thumb3

LH:index1
LH:index2
LH:index3

LH:middle1
LH:middle2
LH:middle3

LH:ring1
LH:ring2
LH:ring3

LH:pinky1
LH:pinky2
LH:pinky3
```

这些节点对应项目中 `key_links` 的 16 个左手链接。

每帧建议保存：

```text
frame
time
node name
world position
world quaternion
```

不要只保存 action。action 是控制输入，不能直接作为 Blender 的骨骼姿态。

---

## 二、无头环境需要修改的两个地方

当前项目的 `main.py` 在测试模式下无条件调用：

```python
env.render()
```

位置大约在：

```text
main.py:540
```

而 `env.render()` 会创建 viewer：

```python
self.viewer = self.gym.create_viewer(...)
```

无头环境中应该跳过这个调用。

### 1. 修改命令行参数

打开：

```text
main.py
```

找到参数定义区域，加入：

```python
parser.add_argument(
    "--headless",
    action="store_true",
    default=False,
    help="Run evaluation without creating an Isaac Gym viewer"
)
```

### 2. 修改 viewer 创建逻辑

找到：

```python
if settings.test:
    ...
    env.render()
    test(env, model)
```

改成：

```python
if settings.test:
    if settings.ckpt is not None and os.path.exists(settings.ckpt):
        assert os.path.exists(settings.ckpt)
        if os.path.isdir(settings.ckpt):
            ckpt = os.path.join(settings.ckpt, "ckpt")
        else:
            ckpt = settings.ckpt
            settings.ckpt = os.path.dirname(ckpt)

        if os.path.exists(ckpt):
            print("Load model from {}".format(ckpt))
            state_dict = torch.load(
                ckpt,
                map_location=torch.device(settings.device)
            )
            model.load_state_dict(
                state_dict["model"],
                strict=False
            )

    if not settings.headless:
        env.render()

    test(env, model)
```

这样：

- 有显示器时：正常创建 viewer；
- 无头环境时：不会创建 viewer；
- `env.step()` 仍然可以正常进行物理仿真。

---

## 三、无头环境的关键问题：不能依赖 `request_quit`

当前 `main.py` 中的 `test()` 使用：

```python
while not env.request_quit:
```

有 viewer 时，按 ESC 或关闭窗口可以退出。

无头环境没有 viewer，因此：

```python
env.request_quit
```

不会成为可靠的停止条件。

应该改成固定帧数，例如：

```python
def test(env, model, record_path=None, max_steps=2400):
    model.eval()
    env.eval()
    env.reset()

    recorder = None
    if record_path is not None:
        recorder = MotionRecorder(env, record_path)

    for step_id in range(max_steps):
        obs, info = env.reset_done()

        seq_len = info["ob_seq_lens"]
        actions = model.act(obs, seq_len - 1)

        obs_, rews, dones, info = env.step(actions)

        if recorder is not None:
            recorder.capture(step_id, env)

        if torch.all(dones):
            print("All environments finished at step", step_id)
            break

    if recorder is not None:
        recorder.close()
```

然后将原来的：

```python
test(env, model)
```

改为：

```python
test(
    env,
    model,
    record_path="recordings/left_hand_motion.json",
    max_steps=2400
)
```

---

## 四、录制函数

建议在 `main.py` 或单独文件中加入：

```python
import json
import os


LEFT_HAND_LINKS = [
    "LH:wrist",

    "LH:thumb1",
    "LH:thumb2",
    "LH:thumb3",

    "LH:index1",
    "LH:index2",
    "LH:index3",

    "LH:middle1",
    "LH:middle2",
    "LH:middle3",

    "LH:ring1",
    "LH:ring2",
    "LH:ring3",

    "LH:pinky1",
    "LH:pinky2",
    "LH:pinky3",
]


class MotionRecorder:
    def __init__(self, env, output_path):
        self.env = env
        self.output_path = output_path
        self.frames = []

        os.makedirs(
            os.path.dirname(output_path) or ".",
            exist_ok=True
        )

        self.link_ids = {}
        for link_name in LEFT_HAND_LINKS:
            link_id = env.gym.find_actor_rigid_body_handle(
                env.envs[0],
                env.actors[0],
                link_name
            )
            if link_id < 0:
                raise RuntimeError(
                    "Cannot find rigid body: {}".format(link_name)
                )
            self.link_ids[link_name] = link_id

        self.fps = env.fps

    def capture(self, frame_id, env):
        env.refresh_tensors()

        state = env.link_tensor[0]

        frame = {}

        for link_name, link_id in self.link_ids.items():
            position = state[link_id, 0:3].detach().cpu().tolist()
            quaternion = state[link_id, 3:7].detach().cpu().tolist()

            # Isaac Gym uses quaternion order x, y, z, w.
            frame[link_name] = {
                "position": position,
                "quaternion": quaternion,
            }

        self.frames.append(frame)

    def close(self):
        output = {
            "fps": self.fps,
            "frames": self.frames,
        }

        with open(self.output_path, "w", encoding="utf-8") as handle:
            json.dump(output, handle, indent=2)

        print(
            "Saved {} frames to {}".format(
                len(self.frames),
                self.output_path
            )
        )
```

不过这里有一个重要注意事项：

## 五、当前项目的 `env.link_tensor` 可能不是左手独立索引

对于 `ICCGANLeftHand`，环境中通常只有左手角色，但 `env.link_tensor` 的刚体顺序仍然由 Isaac Gym 的 actor/body 顺序决定。

不能完全假设：

```python
env.link_tensor[0, link_id]
```

一定就是正确索引。

更稳妥的方式是先打印所有刚体名称：

```python
for body_id in range(
    env.gym.get_actor_rigid_body_count(
        env.envs[0],
        env.actors[0]
    )
):
    body_name = env.gym.get_actor_rigid_body_name(
        env.envs[0],
        env.actors[0],
        body_id
    )
    print(body_id, body_name)
```

建议临时加入到环境初始化后，确认输出类似：

```text
0 guitar
1 LH:wrist
2 LH:wrist_dx
3 LH:wrist_dy
4 LH:wrist_dz
5 LH:palm
6 LH:thumb1
...
```

如果存在辅助节点：

```text
LH:wrist_dx
LH:wrist_dy
LH:wrist_dz
```

录制时可以只保存 16 个主要动作节点，暂时不保存这些辅助节点。

---

## 六、建议先录制一个短片段

不要一开始录整首曲子，先验证 10 秒到 20 秒。

例如：

```python
max_steps = 1200
```

如果环境的 `fps` 是 60，则：

```text
1200 步 ≈ 20 秒
```

输出文件：

```text
recordings/left_hand_motion.json
```

推荐初始测试：

```text
frames = 600
fps = 60
时长 ≈ 10 秒
```

这样容易检查：

- 策略是否成功加载；
- 环境是否正常运行；
- `dones` 是否提前结束；
- 导出的四元数是否稳定；
- Blender 播放速度是否正确。

---

## 七、无头 Isaac Gym 的启动参数

在无头机器上，优先尝试：

```bash
python main.py cfg/left_demo.py ^
  --ckpt pretrained/canon_in_d_major1 ^
  --note assets/notes/canon_in_d_major1.json ^
  --test ^
  --headless ^
  --device 0
```

Linux 机器使用反斜杠：

```bash
python main.py cfg/left_demo.py \
  --ckpt pretrained/canon_in_d_major1 \
  --note assets/notes/canon_in_d_major1.json \
  --test \
  --headless \
  --device 0
```

如果该环境中的 `main.py` 参数不是 `--ckpt` 而是其他形式，以实际 `python main.py --help` 输出为准。

如果出现 EGL、viewer 或 OpenGL 相关错误，确认代码没有调用：

```python
env.render()
```

另外，可以显式让 graphics device 不参与：

```python
env = env_cls(
    num_envs,
    graphics_device=-1,
    compute_device=settings.device,
    ...
)
```

但具体是否接受 `graphics_device=-1`，取决于你部署的 Isaac Gym Preview 4 版本。建议先使用：

```python
graphics_device=settings.device
```

但不创建 viewer；如果仍然初始化图形上下文失败，再尝试 `-1`。

---

## 八、用左手预训练模型，还是双手模型？

如果目标是录制左手动作，优先使用：

```text
cfg/left_demo.py
```

配合左手模型，例如：

```text
pretrained/canon_in_d_major1
```

这比直接使用双手配置更容易排错。

推荐顺序：

### 第一轮

```text
ICCGANLeftHand
cfg/left_demo.py
pretrained/canon_in_d_major1
```

只录制：

```text
LH:wrist
LH:thumb*
LH:index*
LH:middle*
LH:ring*
LH:pinky*
```

### 第二轮

确认左手动作正确后，再使用：

```text
ICCGANTwoHands
cfg/two_demo.py
```

此时同时录制：

```text
LH:* 
RH:*
```

否则左手策略和右手策略同时出问题时，较难判断到底是哪一侧失败。

---

## 九、录制前必须检查的事项

### 1. `settings.test` 下的 episode length

`main.py` 中有：

```python
if settings.test:
    env.episode_length = 500000
```

这适合交互式 viewer，但不适合无限录制。你应当用自己的：

```python
max_steps
```

控制录制长度。

### 2. 不要保存整个 GPU Tensor

不要直接保存：

```python
env.link_tensor
```

应该每帧调用：

```python
.detach().cpu().tolist()
```

否则会：

- 持续占用显存；
- 保存大量不可序列化对象；
- 可能导致显存逐步增长。

### 3. 记录真实的仿真帧率

环境默认参数是：

```python
fps=30
frameskip=2
```

在某些吉他环境中会被配置覆盖为：

```python
fps=60
frameskip=2
```

因此最终必须以：

```python
env.fps
```

作为导出文件的 FPS，不要手写成 60 或 120。

### 4. 注意 `env.reset_done()`

如果动作中途 `done`，直接连续保存会造成：

```text
上一段动作 → 初始姿态 → 下一段动作
```

出现跳变。

第一版可以先设置足够长的 episode，并检查：

```python
if torch.any(dones):
    print("done at", step_id)
```

如果确实发生 reset，建议在输出中加入：

```json
{
  "reset": true
}
```

或者拆分成多个动作片段，而不是把 reset 前后拼成一段动画。

---

## 十、与现有 Blender 导入器的格式差异

之前的 Blender 脚本读取的是：

```json
{
  "LH:wrist": [x, y, z, w]
}
```

而建议的录制格式是：

```json
{
  "LH:wrist": {
    "position": [x, y, z],
    "quaternion": [x, y, z, w]
  }
}
```

建议使用下面的格式，原因是它同时保存了：

- 世界位置；
- 世界旋转；
- 后续可以重新计算局部旋转；
- 更适合策略输出后的仿真状态。

之后 Blender 导入器需要改成：

```python
value = frame[name]

position = value["position"]
quaternion = value["quaternion"]

obj.location = Vector(position)
obj.rotation_quaternion = q_xyzw_to_blender(quaternion)
```

但如果你想尽快验证，也可以先只导出旋转，将动作格式转换成现有脚本兼容的形式。

---

## 推荐的完整验证流程

### 在 Isaac Gym 机器上

1. 修改 `main.py`，增加 `--headless`；
2. 跳过 `env.render()`；
3. 将 `test()` 改成固定 `max_steps`；
4. 使用 `cfg/left_demo.py`；
5. 加载一个已有左手 checkpoint；
6. 录制 600 帧；
7. 保存：
   ```text
   recordings/left_hand_motion.json
   ```
8. 打印并确认：
   ```text
   fps
   frame count
   body names
   quaternion range
   ```

### 在 Blender 机器上

1. 将 JSON 复制到项目相同目录结构；
2. 修改导入器读取 `position/quaternion`；
3. 运行：
   ```powershell
   blender --python tools/import_motion_test.py
   ```
4. 播放 10 秒动作；
5. 检查是否存在突然跳变；
6. 再进行网格和角色重定向。

**结论：无头显卡不影响录制，反而更适合批量导出。真正需要改的是 viewer 依赖、停止条件和姿态保存逻辑。**