# T-pose 源骨架与双手动画

使用本目录新版文件替换之前导入的双手骨架。源场景和旧版导出均保留。

## 文件与教程对应关系

- `hands_mocap.blend`：推荐 Append → Object → `Hands_Mocap_Source`。
- `hands_mocap.fbx`：等价的骨架动画交换文件；导入 Blender 时关闭 Automatic Bone Orientation，Animation Offset 设 0。
- Source Armature：`Hands_Mocap_Source`（若场景已有同名物体，Blender 会加数字后缀）。
- 命名标准：Mixamo，带 `mixamorig:` 前缀。参考静止姿态为 T-pose，包含 Hips、脊柱、头、双臂、双腿及完整五指，共 52 根骨骼。
- Root：`mixamorig:Hips`；ARP 默认目标为 `c_root_master.x`，必须勾选 **Set as Root**。
- `hands_mixamo_ik.bmap`：推荐配置，已包含 Hips 根映射和 32 项双手映射。
- `hands_mixamo_fk.bmap`：同样标记 Hips，但手腕只传旋转；完整手腕轨迹请使用 IK 版。

之前版本报错是因为配置缺少任何 Set as Root 项。新版有唯一 Hips 根骨，并在 `.bmap` 中明确标记；仅增加骨头、却不在 ARP 映射里勾选该项，仍然会报错。

## 操作步骤

1. 导入新版源骨架，设置场景 60 FPS。不要把旧版 `Hands_Mocap_Source` 误选为 Source。
2. 在骨架数据属性的 **Skeleton → Rest Position** 查看 T 字姿态；播放前切回 **Pose Position**。T-pose 是骨架的静止参考姿态，不是动画第 0 帧，也没有插入额外动作帧。
3. ARP Remap 设置 Source 为新版骨架，Target 为目标 ARP 控制骨架；在当前项目 `quin.blend` 中是 `rig`。
4. **Build Bones List → Import Mapping**，导入本目录 `hands_mixamo_ik.bmap`，启用 Clear Current Bones List。
5. 选中映射列表的 `mixamorig:Hips`，确认 Target 为 `c_root_master.x`，**Set as Root 已勾选**。如果只按教程加载内置 Mixamo 配置，也必须检查这一项；推荐使用本目录配置。
6. 确认 `LeftHand` / `RightHand` 对应 `c_hand_ik.l` / `c_hand_ik.r`，启用 IK、IK World Space，目标双臂使用 IK。手指对应 `c_thumb1.l` 等默认 ARP 控制器。
7. 核对源/目标的朝向、尺度与参考姿态，需要时使用 Redefine Rest Pose。参考骨架面向 Blender +Y，左手位于身体中心的 -X 一侧，与本次记录的左右手空间分布一致。不要因模型比例不同盲目 Auto Scale：源双手保留真实米制尺寸，辅助身体尺寸是人为选取的。
8. Retarget，帧范围 **0–599**。FBX 若使用默认 Animation Offset=1，改为 **1–600**。

## 数据含义

32 根手部骨骼的运动来自原始场景，保留手腕/指节世界位置、旋转与时间。手部静止姿态由 MJCF 的零关节角布局构建，四指展开、拇指外展；它不再使用原第 0 帧弯曲手势作为静止姿态。

20 根躯干/肢体骨骼为辅助结构，不含真实全身动捕。Hips、躯干和腿静止；双臂按固定骨长、预设肘部方向解算至记录的手腕位置，供查看层级和动作。手腕动画仍由源场景独立烘焙，不受合成手臂修改。辅助身体放置于当前记录的动作范围附近，以使手臂可达。

推荐映射只包含 **Hips + 双手，共 33 项**，不把推算的手臂或静止腿部作为测量数据传给目标。Hips 映射满足 ARP 要求，并会参与目标根的重定向；若目标已有全身动画，需要在实际工作流中管理根动作。目标肘部由目标 IK/pole 设置决定，手指长度不同仍可能需要接触修正。

## 验证与重新生成

`validation.json` 记录全部 600 帧的原生烘焙和 FBX 回读误差。`arp_mapping_validation.json` 记录本机 ARP 实际导入两份配置的检查：唯一 Hips 根映射、33 项均找到 `quin.blend` 的 `rig` 目标控制器、双手 IK 选项正确。此项是配置导入验证，不代表目标角色的最终重定向视觉效果已经调整完成。

```powershell
blender --background --factory-startup --python-exit-code 1 --python tools/export_hand_mocap.py -- --tpose
blender --background --python-exit-code 1 --python tools/verify_hand_tpose_arp.py
```

第二条命令需要本机 ARP 已启用；只在内存中载入 `quin.blend` 做检查，不保存或覆盖角色场景。
