# 源模型验证场景

直接打开 `source_validation.blend`，在时间轴或 3D 视图内按空格播放。

- **动画**：0–599 帧，60 FPS，约 10 秒；打开时停在第 120 帧。
- **颜色**：蓝色左手，橙色右手；绿色小点为源模型指尖参考，黄色小点为拨片参考。
- **相机**：`Camera Overview`、`Camera Left contact`、`Camera Right contact`。在 Outliner 选中相机后，在 3D 视图按 `Ctrl + 小键盘 0` 将其设为当前相机；`小键盘 0` 切换相机视图。也可以直接旋转视图检查。
- **时间轴标记**：0（启动）、120（检查姿态）、203（较大位移）、565/570（快速转动）、599（结尾）。
- **集合**：`03 Source hand meshes` 为手网格，`04 Guitar and strings` 为吉他和琴弦，`05 Contact references` 为参考点及拨弦范围框。可在 Outliner 切换显示。
- 原始动画在 `01 Recorded world poses` 中；`02 Fixed source frames` 存放固定子节点。辅助坐标轴默认隐藏，避免挡住模型。取消对象隐藏后，还需在视图叠加设置中启用 Extras 才能查看轴。

## 还原范围

源手网格共 34 个部件：每手 wrist、palm 和 15 个指节。按照 MJCF 的 mesh scale 和 geom 局部位姿放置，直接跟随 JSON 的刚体世界姿态，不添加平滑或接触修正。

琴颈、22 品、弦枕、琴身方盒和拨弦范围来自仓库 MJCF；六根弦按其端点绘制，显示半径为 0.22 毫米，仅作位置参考。仓库没有完整琴身外观网格，因此方盒是源仿真代理形状，并非导入缺失。

录制没有吉他姿态，使用源 MJCF 中固定的吉他位置和旋转；掌部、指尖和拨片参考点通过固定层级推导。黄色小点表示 `RH:pick` 的参考位置，不代表真实拨片的形状。所有网格及关键帧均保存在 .blend 中，播放不依赖外部 JSON 或 Python。

**这个场景用于检查源动作，尚未进行角色重定向，也未验证曲谱对应的接触正确性。** 绿色点是参考点，不表示正在接触。检查时尤其留意开头的快速位移和 565–571 帧的指节变化。

## 产物与验证

- `overview_0120.png`：总览。
- `left_*.png` / `right_*.png`：关键帧特写。
- `validation.json`：600 帧逐帧核对误差及关键帧的吉他局部指尖/拨片坐标，单位为米。
- 保存文件后重新启动 Blender，检查 8 个关键帧、固定接触点偏移，以及 36 个源网格的原始顶点范围、缩放和位置偏移。

在项目根目录重新生成（覆盖指定输出场景）：

```powershell
blender --background --factory-startup --python-exit-code 1 --python tools/build_source_scene.py -- --render
```

验证保存后的文件：

```powershell
blender --background blender/source_validation/source_validation.blend --python-exit-code 1 --python tools/verify_source_scene.py
```

构建器面向当前仓库源资产；对含 reset 的录制或四元数符号不连续的录制会报错，避免自动拼接出错误动画。自定义文件可通过 `--motion` 和 `--output` 指定。源资产许可保留在原 MJCF 文件中。
