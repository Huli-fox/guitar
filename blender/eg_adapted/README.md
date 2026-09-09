# EG 吉他动作适配

## 前倾持琴版本

`hands_on_EG_forward.blend` 是基于本目录原适配场景的姿态微调版：上半身绕腰部前倾 12°，吉他和双手一起向身前（世界 -Y）移动 16 厘米，肘部重新解算为向前、向外弯曲。双手相对吉他的完整动作保持不变；物体原点、朝向、静止骨架、髋部及双腿保持原样。原 `hands_on_EG.blend` 保留用于比较。

- 动画：`Hands_EG_Forward_Lean_60fps`，0–599 帧 / 60 FPS。
- FBX：`hands_EG_forward.fbx`，只包含源人体骨架。
- ARP 配置：`hands_forward_ik.bmap`，在原 33 项映射上增加脊柱、颈、头和肩部，共 40 项。要传递上半身前倾请使用此配置；原来的纯手部配置不会传递脊柱变化。目标肘部方向仍受目标角色 IK pole 设置影响。
- 预览：`forward_overview_0120.png`、`forward_side_0120.png` 和双手特写。
- 验证：`forward_posture_validation.json`，保存后 600 帧及 FBX 回读均通过，手臂关节连接和手与琴的相对动作得到保留。
- 重新生成：`blender --background --factory-startup --python-exit-code 1 --python tools/lean_eg_posture.py`。

重定向前倾版时，一起导入此版本中的吉他层级，避免使用原版本尚未前移的吉他位置。

打开 `hands_on_EG.blend`，按空格播放。场景已放入 EG 吉他和适配后的源骨架，停在第 120 帧；动画范围 0–599，60 FPS。

## 文件

- `hands_on_EG.blend`：完整适配场景，包含 `Hands_Mocap_Source` 和 EG 的 `Guitar_Rig` / 模型层级。
- `hands_EG_motion.fbx`：适配后的 52 骨动画，仅源人体骨架，不含吉他。Blender 导入时关闭 Automatic Bone Orientation，Animation Offset 设 0。
- `hands_mixamo_ik.bmap`：ARP 映射；Hips → `c_root_master.x`，已标记 Set as Root，双手使用 IK World Space。与此前成功使用的配置相同。
- `overview_0120.png`、`left_0120.png`、`right_0120.png`：第 120 帧总览与双手预览，蓝色左手、橙色右手。图中的彩色骨段为渲染辅助物，未写入工作场景。
- `adaptation.json`：适配参数与求解误差；`verification.json`：保存文件和 FBX 回读验证。
- `landmarks.json`：两把琴的六弦及品位参考点；`tip_targets.json`：600 帧映射后的十个指尖目标，用于复核。

## 保留和调整的内容

输入为你手工修正过的 `../hand_mocap_tpose/hands_mocap.blend`，没有重新生成旧骨架。保留脚下居中的物体原点、朝向、T-pose 静止骨架、全部骨长和根动作。通过源手部节点与修正后骨架的位置拟合坐标变换，误差约 0.0002 毫米。

EG 保持原始米制尺寸、模型形状、材质和吉他骨架层级，只整体旋转和平移至原动作的持琴位置。模型额外的第 23、24 品仍保留；动作对应使用源琴已有的第 1–22 品和六弦。

适配沿琴颈保留同一品间的相对位置，横向保留同一弦间的相对位置，并保留指尖相对弦面的高度。实际琴弦参考来自 EG 弦网格，未用位于调弦器附近的物体原点替代。六弦由低到高对应 EG 的 `String E / A / D / G / B / E2`。

手腕和手指重新烘焙；指尖由固定骨长的三节链求解，必要时轻微调整手腕使五指目标同时可达。辅助上臂/前臂随后重新求解到手腕，躯干和下肢保持输入动作。当前手腕最大世界位移调整约 20.44 毫米，其中可达性补偿最大约 7.05 毫米。

这是基于源场景几何关系的动作适配。源动作中抬起的手指仍抬起，没有把全部手指强制吸附到琴弦，也没有推断乐谱、按弦力或消除源动作自带的穿插。没有添加实体拨片；右手保留原指尖/拨弦区域的几何对应，未单独约束源 `RH:pick` 参考点。

## 继续在 Auto-Rig Pro 中使用

1. 将本场景的 `Hands_Mocap_Source` 和 `EG Guitar - original dimensions` Collection Append 到目标角色场景，或直接在本场景中加入目标角色。
2. Source 选择 `Hands_Mocap_Source`，动作选择 `Hands_EG_Adapted_60fps`；Target 选择你的 ARP 控制骨架。
3. Build Bones List 后导入本目录 `hands_mixamo_ik.bmap`。确认 Hips 的 Set as Root、双手 IK / IK World Space。
4. 重定向 0–599 帧（60 FPS）。如果移动、旋转整体持琴位置，请将吉他和源骨架一起变换，避免破坏二者的相对关系。
5. 源骨架已适配 EG；目标角色的手指长度和参考姿态不同，仍可能需要目标侧手部 IK / 接触微调。当前没有改写 `quin.blend` 或替你覆盖既有重定向结果。

## 验证

保存后重新载入并检查全部 600 帧：用户原点、朝向和静止骨架保留；骨长与关节连接误差低于 0.001 毫米；指尖距几何映射目标最大误差低于 0.001 毫米。EG 实际弦参考点位置符合原模型的刚体变换。FBX 回读骨骼位置最大误差约 0.001 毫米。

上述指尖误差是相对生成的几何目标，不是相对真实按弦接触的测量精度。

重新生成（只更新本目录，不覆盖两个输入文件）：

```powershell
blender --background --factory-startup --python-exit-code 1 --python tools/adapt_hands_to_eg.py
blender --background --factory-startup --python-exit-code 1 --python tools/verify_eg_adaptation.py
blender --background --factory-startup --python-exit-code 1 --python tools/render_eg_adaptation.py
```
