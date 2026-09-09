# 双手动作导出（Auto-Rig Pro）

**更新：请优先使用 `../hand_mocap_tpose/`。本目录旧版只有双手，没有 ARP 必需的 Hips / Set as Root 映射；新版提供 T-pose 层级并修复此问题。**

源文件：`../source_validation/source_validation.blend`。导出仅包含双手骨架，没有吉他或网格。

## 文件

- `hands_mocap.blend`：推荐使用，原生四元数动画，Source Armature 为 `Hands_Mocap_Source`。
- `hands_mocap.fbx`：仅骨架与动画，可导入其他场景。Blender 导入时关闭 Automatic Bone Orientation；Animation Offset 设为 0 可保留原帧号，默认偏移 1 时使用 1–600 帧。
- `hands_mixamo_ik.bmap`：推荐的 ARP 自定义映射；手腕 → `c_hand_ik.l/r`，开启 IK / IK World Space，手指 → `c_thumb1.l` 等控制器。
- `hands_mixamo_fk.bmap`：只传手腕及手指旋转的 FK 映射；不传手腕移动轨迹。
- `bone_mapping.json`：32 个原始节点、导出骨骼、ARP FK 控制器的对应表；这是说明数据，不是 ARP 的配置导入格式。
- `validation.json`：600 帧原生骨架及 FBX 回读与源姿态的误差。

## 命名标准与数据范围

采用 **Mixamo 手部命名子集**：`mixamorig:LeftHand` / `RightHand`，以及各侧 `HandThumb1–3`、`HandIndex1–3`、`HandMiddle1–3`、`HandRing1–3`、`HandPinky1–3`。共 32 根骨骼，每只手腕为独立根骨。

这是源仿真动画转换得到的骨骼动画，不是 Mixamo 网站下载的全身动捕；没有 Hips、肩、上臂或前臂。若使用内置标准，可参照 Mixamo（带 `mixamorig:` 前缀），但优先导入随附 `.bmap`，避免全身预设的缺失骨骼映射。

动画为 60 FPS，0–599 帧，600 个样本，约 10 秒。保留原场景世界坐标、米制尺度及双手位移；没有平滑、重采样或接触修正。骨骼以原第 0 帧为静止参考姿态，骨头沿指节方向建立，不是标准全身 T-pose。掌部固定偏移已包含在手指相对手腕的变换中。

## 在 ARP 中使用

1. 将 `.blend` 中的 `Hands_Mocap_Source` Object 通过 Append 加入角色场景，或导入 FBX。场景帧率设为 60 FPS。
2. 在 ARP Remap 中设置 Source Armature 为导入的骨架，Target Armature 为已生成的 ARP 角色控制骨架；源 Action 为 `Hands_Mocap_60fps`（FBX 导入后名称可能变化）。
3. Build Bones List，然后通过映射配置 Import 导入 `hands_mixamo_ik.bmap`。核对 32 项目标控制器均存在；自定义目标命名需要修改对应项。
4. 目标双臂切换到 IK。检查两只手映射到 `c_hand_ik.l/r`，并启用 IK 与 IK World Space；手指使用常规旋转映射。不需要虚构肘部 pole 映射或上臂源骨骼。
5. 对齐源/目标的尺度、位置和参考手势；按需要用 ARP 的 Redefine Rest Pose 对齐参考姿态，之后重定向 0–599 帧。不要直接把第 0 帧的弯曲手势当作目标角色张开的手掌参考姿态。
6. 检查手腕轨迹、拇指朝向和手指弯曲。目标臂长、肘部朝向与源数据没有对应测量，需由目标 IK 设置决定；手指长度不同也可能需要后续接触调整。

随附配置针对 ARP 默认控制器名称。导出与 FBX 回读已逐帧验证；配置按本机 ARP 格式生成，但尚未在你的目标角色上完成重定向验证。FBX 的欧拉角转换会引入少量旋转误差，优先使用原生 `.blend` 可避免这一步转换。

## 重新生成

在项目根目录执行（更新本目录产物，不覆盖源场景）：

```powershell
blender --background --factory-startup --python-exit-code 1 --python tools/export_hand_mocap.py
```
