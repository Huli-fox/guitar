# 弹奏动作 → T-pose 源骨架 → 目标吉他适配 → ARP 重定向

整理日期：2026-09-09。本文描述本次实际完成的流程，以及当前脚本的复用边界。

## 1. 输入和输出是什么？

从使用者角度，主要输入是 **带弹奏动画的源场景 + 实际要使用的吉他模型**；主要输出是 **带烘焙动画的 Source Armature `.blend`**。本次最终 `.blend` 同时包含已摆放好的目标吉他，方便检查按弦、拨弦和持琴姿势。

但当前实现不是仅凭任意两个 `.blend` 就能自动适配的通用工具：它还依赖本项目的手部结构定义、骨骼命名和吉他几何标定。

| 输入 | 本次文件 | 作用 |
| --- | --- | --- |
| 源动画场景 | `blender/source_validation/source_validation.blend` | 已记录双手刚体节点动画，包含源参考吉他及其琴弦、品位、指尖参考点 |
| 手部结构定义 | `assets/left_hand_guitar.xml`、`assets/right_hand.xml` | 提供 MJCF 零关节角参考姿态、固定偏移、指节层级与指尖位置 |
| 目标吉他模型 | `blender/EG.blend` | 最终使用的电吉他；保留原尺寸，标定六弦和品位 |
| 用户修正过的中间骨架 | `blender/hand_mocap_tpose/hands_mocap.blend` | 已把原点移到双脚中间，并旋转为前视图正面朝向；适配阶段以此为输入 |
| ARP 目标角色（下游） | 本项目 `blender/quin.blend` 中的 `rig` | 接收 Source Armature 动画；不是制作源骨架的必需输入，但本机映射验证使用它 |

“实际吉他模型”指目标三维资产，不是照片或真实吉他的自动扫描输入。

若从更上游开始，还需 `recordings/left_hand_motion.json` 及 MJCF 引用的网格资源。`tools/build_source_scene.py` 用这些数据构建源场景。已有有效源场景时，不必重做此阶段。

### 当前最终交付

| 文件 | 内容 / 用途 |
| --- | --- |
| `blender/eg_adapted/hands_on_EG_forward.blend` | 最终前倾持琴版：52 骨源人体骨架 + EG 吉他完整层级；600 帧 / 60 FPS |
| `blender/eg_adapted/hands_EG_forward.fbx` | 同版源人体骨架与动画，不含吉他 |
| `blender/eg_adapted/hands_forward_ik.bmap` | ARP 映射，包含根、双手和上身，共 40 项 |
| `blender/eg_adapted/hands_on_EG.blend` | 前倾调整之前的 EG 适配场景，用于对照 |
| `blender/eg_adapted/forward_*_0120.png` | 总览、侧面与双手预览 |
| `blender/eg_adapted/*validation.json`、`verification.json`、`adaptation.json` | 动作保存、导出和几何适配的验证报告 |

最终 Source Armature 名称：`Hands_Mocap_Source`。前倾版动作：`Hands_EG_Forward_Lean_60fps`。这些是**可供重定向的源动画资产**，不是已经替任意目标角色完成重定向的结果；本次没有覆盖 `quin.blend` 的角色动画。

## 2. 工作流各阶段

```text
录制 JSON + MJCF / 源网格（已有源场景时可跳过）
    ↓ build_source_scene.py
带动画的源场景 + 源参考吉他
    ↓ export_hand_mocap.py --tpose（另读取 MJCF）
Mixamo 命名的 52 骨 T-pose 源骨架 + 动画 + ARP 配置
    ↓ 用户坐标修正：原点置于脚下中间、旋转为正面朝向
用户确认的 hands_mocap.blend
    ↓ adapt_hands_to_eg.py ← EG.blend + 原源场景
hands_on_EG.blend：目标吉他原尺寸 + 按琴弦 / 品位适配的动作
    ↓ lean_eg_posture.py
hands_on_EG_forward.blend：前倾、手臂前伸的最终版
    ↓ ARP Remap + 目标角色
目标角色动画（检查比例、IK 与接触，按需微调）
```

### 源刚体动画转换为骨骼动画

源场景最初没有 Armature，运动由 `LH:*`、`RH:*` 刚体节点承载。逐帧采样世界变换，构建双手骨骼并烘焙位置、四元数旋转和尺度。

最初仅导出双手的 32 骨版本缺少根映射，ARP 提示必须 Set as Root。最终改为 52 骨 T-pose 层级：32 根有源数据的手部骨骼，20 根辅助身体 / 肢体骨骼，唯一根为 `mixamorig:Hips`。

命名沿用 Mixamo；不代表该数据来自 Mixamo 或包含真实全身动捕。躯干、腿是辅助结构，手臂 / 肘部由手腕位置推算。手指参考姿态使用 MJCF 零关节角布局，而非第 0 帧的弯曲手势。T-pose 是 Rest Position，动画仍从原弹奏帧开始。

辅助身体曾因朝向与源左右手空间分布相反造成交叉，已修正。随后用户又完成原点和正面朝向调整；后续适配保留这些改动。

### 保留 EG 尺寸，调整手部动作

目标琴的弦长、弦距、品位间隔及弦面高度不同，不能只将模型搬到源琴位置。

1. 从原源场景和用户修正后的骨架拟合刚体坐标变换，恢复源参考琴在新坐标系中的位置。
2. 读取 EG 六弦实际网格参考点，以及 `Fret.000` 等品位对象；琴弦对象原点位于调弦器附近，不能作为按弦参考。
3. 按源琴与 EG 的同编号琴弦、同编号品位建立映射：保持品间 / 弦间相对位置及距弦面高度。
4. 只刚性摆放 EG，不缩放或变形模型。当前标定源琴第 1–22 品；EG 第 23、24 品仍保留在模型中。
5. 映射指尖目标，保留指节长度，通过三节指链求解弯曲；必要时微调手腕，使五指目标可达，再解算上臂 / 前臂。
6. 保存为独立场景，导出仅骨架的 FBX，并回读核对。

当前适配手腕最大调整约 20.44 毫米，可达性补偿最大约 7.05 毫米。这里验证的是相对几何目标的误差，不等同于音乐正确性或真实接触精度。

### 前倾与手臂前伸

最终版以当前 `hands_on_EG.blend` 为输入，上身绕腰部前倾 12°，吉他与双手共同向世界 -Y 前移 16 厘米，重新解算肘部，使其向前、向外弯曲。

手与琴的相对动作保持不变；物体原点、旋转、静止骨架、髋部和下肢保留。另存 `hands_on_EG_forward.blend`，便于与原姿态比较。前倾参数和方向目前写在脚本中，不是通用的身体姿势识别。

## 3. 实际使用的工具和脚本

环境：本机 Blender 5.2.1，后台 Python，`bpy`、`mathutils`、Blender 自带 NumPy，以及 FBX 导入 / 导出器。ARP 只用于下游重定向与配置导入检查；源动作转换、吉他适配、前倾求解不依赖 ARP 执行。

| 脚本 | 用途 | 当前定位 |
| --- | --- | --- |
| `tools/build_source_scene.py` | JSON + MJCF / 网格 → 源场景，可生成检查图 | 可选上游；支持 `--motion`、`--output`、`--render` |
| `tools/verify_source_scene.py` | 检查保存的源节点动画、固定偏移、源网格 | 源资产检查，有当前录制假设 |
| `tools/export_hand_mocap.py --tpose` | 源节点 → T-pose 骨架，烘焙动画，导出 FBX / `.bmap` 并回读 | 主要转换脚本；不带 `--tpose` 是早期双手版本 |
| `tools/verify_hand_tpose_arp.py` | 检查层级、展开手指、手臂连接，实际导入 ARP 配置检查目标骨名 | 依赖已安装 ARP、`quin.blend` 中的 `rig`；部分几何检查针对用户旋转前版本 |
| `tools/render_hand_tpose_preview.py` | 原 T-pose 源骨架动作预览 | 历史检查图，主要针对手工坐标修正前版本 |
| `tools/adapt_hands_to_eg.py` | EG 标定、手部适配、独立 `.blend` / FBX、报告 | EG 专用适配器，不是任意吉他加载器 |
| `tools/verify_eg_adaptation.py` | 回读原点 / 静止骨架、骨长、关节连接、指尖、琴弦几何、FBX | 主要结果检查 |
| `tools/render_eg_adaptation.py` | EG 总览、手部及侧视图 | `--forward` 选择前倾版 |
| `tools/lean_eg_posture.py` | 前倾和持琴空间调整，保存并验证 `.blend` / FBX，生成上身映射 | 当前最终处理阶段 |

原点和正面朝向调整是**用户在 Blender 中完成的手工步骤**，目前没有独立脚本自动复现。不要把完整流程描述成已实现一键重建。

## 4. 执行顺序与覆盖范围

在项目根目录执行。下列命令是当前资产的复现顺序，**生成器会更新固定输出路径**。尤其不要直接重跑骨架导出命令后继续适配：它会覆盖用户修正过的 `hands_mocap.blend`，新骨架还需要重新应用坐标修正。

先保存每个曲目的源场景、中间骨架和最终输出副本，或将脚本路径改为曲目独立目录。

```powershell
# 可选：从录制重建源场景；更新其输出文件
blender --background --factory-startup --python-exit-code 1 --python tools/build_source_scene.py -- --render

# 更新源骨架输出；此后在 Blender 中重新完成 / 复用坐标修正
blender --background --factory-startup --python-exit-code 1 --python tools/export_hand_mocap.py -- --tpose

# 确认中间骨架和原源场景是同一曲目，再执行适配
blender --background --factory-startup --python-exit-code 1 --python tools/adapt_hands_to_eg.py
blender --background --factory-startup --python-exit-code 1 --python tools/verify_eg_adaptation.py

# 最终姿态微调、内部回读验证，以及预览
blender --background --factory-startup --python-exit-code 1 --python tools/lean_eg_posture.py
blender --background --factory-startup --python-exit-code 1 --python tools/render_eg_adaptation.py -- --forward
```

`adapt_hands_to_eg.py` 不覆盖输入源场景、用户骨架和 `EG.blend`；`lean_eg_posture.py` 不覆盖原 EG 适配场景。它们会覆盖各自的既有输出版本。

### ARP 最后一步

使用最终场景中的 `Hands_Mocap_Source`、`Hands_EG_Forward_Lean_60fps` 和同一场景的吉他层级。Source / Target 设置后 Build Bones List，导入 `hands_forward_ik.bmap`，确认 `mixamorig:Hips → c_root_master.x` 且 Set as Root 已勾选。

纯手部配置 `hands_mixamo_ik.bmap` 有 33 项；最终 `hands_forward_ik.bmap` 增加脊柱、颈、头和肩部，共 40 项，才能传递上身前倾。手腕使用 IK World Space，目标双臂使用 IK；目标肘部仍需合适的 pole 设置。

FBX 在 Blender 中导入时关闭 Automatic Bone Orientation，Animation Offset 设 0；若默认偏移为 1，则原 0–599 帧对应 1–600 帧。源骨架和吉他一起变换，避免破坏相对位置。

## 5. 能适应场景 A 吗？

**A：仅曲谱变化的源场景 + 同一个 EG 模型——流程可复用，是最容易扩展的情况；当前代码仍有需要处理的固定假设。**

如果新曲目仍使用同一套手部 MJCF、相同源参考琴、相同节点名和单位，骨骼命名、层级、EG 几何标定与 ARP 映射可复用。源骨架应从新曲目的节点动画重新烘焙，然后重新适配、微调和验证。不要用旧曲目的 `hands_mocap.blend` 搭配新曲目的源场景，否则坐标拟合比较的是不同姿态，可能报错。

需要特别处理：

- **帧数和帧率**：当前验证和前倾脚本使用 `range(600)`；适配脚本使用 0、120、599 帧做坐标拟合，并在输出中设置 60 FPS。新曲目长度不同，应先统一改为读取有效起止帧、采样帧和输入 FPS。
- **原点 / 朝向**：保存并复用用户的坐标修正，不能因为重新导出而丢失。适配阶段只接受源手部与修正骨架之间统一的刚体变换；额外改手势、缩放或局部改骨架需要重新设计校准。
- **可达性**：辅助身体位置和约 0.32 米上下臂长度为本次动作设置。换把范围变大时，可能触发手臂不可达断言，需调整持琴位置、身体尺寸或姿态后重算。
- **录制连续性**：上游构建器对 reset 边界和四元数符号不连续会拒绝；应先整理录制片段。
- **回归检查**：每首曲目都重新核对全帧、指尖误差、关节连接、左右臂、FBX 和关键换把帧。仅复用标定不代表新动作已验证。

结论：**同资产、同时间规格下可按现流程运行；任意长度的新曲目批处理，需要先参数化时间和路径，并自动复用坐标修正。** 本次没有实际用第二首曲目做验证。

## 6. 能适应场景 B 吗？

**B：不同源场景 + 不同吉他模型——几何映射与求解思路可复用，但现有脚本不能只替换 `.blend` 路径就保证成功，需要重新标定。**

若“不同源场景”仍只是新曲目，源侧要求同 A。若源手部骨架 / 刚体结构也变了，还需要新节点映射、层级、参考姿态和指尖定义；目前只认识本项目的 `LH:*` / `RH:*` 和五指三节结构。

目标新吉他至少需要提供：

| 标定信息 | 用途 |
| --- | --- |
| 单位 / 尺寸、琴颈方向、弦面法向、左右手琴属性 | 确定正确尺度、朝向，避免镜像和反面 |
| 六弦从低音到高音的编号，各弦上弦枕至琴桥的可用段 | 定义弦距、弦面与有效弦长 |
| 上弦枕、各品编号及位置、琴桥参考位置 | 定义同品位对应和沿琴颈映射 |
| 模型根对象、子层级、修改器 / 蒙皮和静止状态 | 保证整把琴刚性摆放，避免子物体重复变换 |
| 可用的指板 / 琴体碰撞表面（若要求接触修正） | 检查不同琴颈厚度、曲面及琴体外形造成的穿插 |

当前 EG 专用部分包括 `Guitar_Rig`、`String E/A/D/G/B/E2`、`Fret.000…` 对象名，以及特定 Z 高度的四顶点弦截面。目标换为合并网格、曲线弦、不同拓扑、不同朝向或不同品数后，必须更换这些参考点提取逻辑。没有弦 / 品网格时，可手工提供标记点；不能直接沿用 EG 的网格坐标。

流程中本次按相同弦号和品号对应，不做变调或换弦编配；不同弦数、调弦、左手琴或品位缺失需要另行确定音乐和空间对应规则。

建议后续把脚本拆成“源手部配置”“目标吉他标定配置”“曲目 / 时间配置”“姿态参数”四部分。通用求解器消费标定点，不直接读取特定模型名字和顶点高度。**这是建议的扩展方向，本次尚未实现。**

## 7. 已验证范围与限制

- 本次完成并检查了一个源录制、EG 模型及本机 ARP 默认控制器命名的工作流；用户确认能够重定向并认可适配与姿态效果。
- 原生动作保存和 FBX 回读均核对 600 帧，验证骨长、链连接、根 / 静止姿态和手琴相对关系。
- 极小数值误差指相对本次计算目标，不表示任意目标角色都能毫米级按弦。目标手型、骨长和参考姿态不同，仍需目标侧调整。
- 没有推断音符正确性、接触力、弦振动或音频同步，也没有自动消除所有源动作穿插。
- 手指求解保持骨长并参考源姿态，但没有施加完整人体关节限位或皮肤碰撞约束。
- 没有添加实体拨片，也未独立约束源 `RH:pick` 点。若需要精确拨片接触，应把拨片姿态和接触点纳入适配。
- 自动全身姿态生成仍为辅助方案；任意新模型 / 新曲目的可达性和视觉合理性需要重新检查。
