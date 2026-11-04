# 中广舒适家 Zhongguang (Gizwits) for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Validate](https://github.com/lsl9119/ha-zhongguang-gizwits/actions/workflows/validate.yml/badge.svg)](https://github.com/lsl9119/ha-zhongguang-gizwits/actions/workflows/validate.yml)

把「中广舒适家」App 里的**中广欧特斯家用变频两联供（空气源热泵）外机**接入 Home Assistant：读取水温、制冷剂侧温度压力、压缩机频率等，并可开关机、切换制热/制冷、设定目标出水温度。

> 非官方项目，与中广欧特斯、机智云（Gizwits）没有任何关系。接口来自对 App 网络请求的观察，厂商随时可能改动。控制的是真实的采暖/制冷设备，请自行评估风险。

English summary: unofficial Home Assistant integration for Zhongguang/Outes air-to-water heat pumps controlled by the "中广舒适家" app (Gizwits cloud). Cloud polling; sign in with the app's phone number + password; tokens renew automatically.

## 功能

- 控制（v0.5.0 起不再用空调式的 `climate` 温控盘，改成和线控器一样分开设定）：
  - `switch` 外机开关
  - `select` 运行模式：制热 / 制冷（只切模式，不顺带开机）
  - `number` 制热出水温度 16–55 °C、制冷出水温度 7–25 °C，步进 1 °C；两个设定值各自独立，任何模式下都能改，越界直接拒绝
  - 原始控制字 `ctrl_raw` 和云端字段 `raw_attrs` 挂在「外机开关」的属性上
- 传感器：出水/回水温度、室外环境温度、翅片/板换/吸气/排气温度、排气饱和温度与压力、排气过热度、压缩机频率、直流风机、AC 输入电压、母线电压、IPM 温度、电子膨胀阀步数、线控器室内温度
- 二值传感器：压缩机运行（按频率）、压缩机运行位（状态位，变化即报，启停沿更准）、云端在线
- token 失效时用保存的账号自动重新登录（见下文）
- 诊断信息下载（token / 密码 / 手机号 / DID 已脱敏）

## 支持的设备

已对照线控器「机组状态」面板逐项验证的型号：

| 产品 | product_key |
|---|---|
| 中广欧特斯 家用变频两联供 | `fb80943e1165424baab2529ca3bdc2ac` |

其他走同一个 App 的中广设备也许能连上，但传感器含义可能不同，集成会在日志里提示。欢迎在 issue 里附上「诊断信息」和线控器面板照片，一起把映射补上。

## 安装（HACS 自定义存储库）

1. HACS → 右上角 ⋮ → **自定义存储库**，填 `https://github.com/lsl9119/ha-zhongguang-gizwits`，类别选 **Integration**
2. 在 HACS 里搜索「中广舒适家」并下载
3. 重启 Home Assistant
4. 设置 → 设备与服务 → 添加集成 → 搜索「中广舒适家」

手动安装：把 `custom_components/zhongguang_gizwits` 复制到 HA 配置目录的 `custom_components/` 下，然后重启。

## 登录方式

添加集成、重新验证、重新配置时都可以选：

| 方式 | 需要什么 | token 失效后 |
|---|---|---|
| 手机号 + 密码 | 中广 App「密码登录」用的账号；没设过密码的先在 App 里设一个 | 自动重新登录 |
| 粘贴加密登录请求 | 抓包得到的 `POST app.outes.com/app/smart_home/login/pwd` 请求体（JSON） | 自动重新登录；不保存明文密码；改了 App 密码要重新粘贴 |
| User Token | 抓包得到的 `X-Gizwits-User-token` 请求头和设备 DID | 只能手动再换 |

> ⚠️ **「手机号 + 密码」方式还在验证中。** 中广登录网关确认能识别明文手机号，但「明文正确密码 → 拿到 token」目前只在同款网关的其他项目里见过，作者还没在中广账号上实测成功。如果你提示「密码错误」而密码确定没错，请改用「粘贴加密登录请求」，并开个 issue 告诉我。

自动续期规则：机智云返回 token 失效（`9004`）时登录一次并重试；同一时间只登录一次，两次自动登录至少间隔 5 分钟；**账号或密码被拒会立即停止并要求重新验证，不会反复尝试**，避免账号被锁。

账号、密码（或加密串）和 token 保存在 HA 本机的配置条目里（`.storage/core.config_entries`），与其他需要登录的集成一样。

## 使用说明与限制

- 目标温度是**外机的目标出水温度**，不是室温。
- 外机大约每 3 分钟才上传一次模拟量，所以温度、频率会有延迟；状态位变化即报。集成每 10 秒轮询一次。
- 云端没有电流数据（线控器上的压机相电流、AC 输入电流都没有上传），所以算不了耗电和 COP。
- 制冷设定值的位置（`Ctrl_Set` 字节 4–5）是推断的，还没在制冷季实写验证。
- 制热最高 55 °C、制冷最低 7 °C 是外机极端天气下会用到的值；制热下限 16 °C、制冷上限 25 °C 没有对照线控器，如果你的线控器范围不同，欢迎提 issue。
- 从 v0.4.x 升级：旧的 `climate` 实体会被自动移除，引用它的仪表盘/自动化需要改成上面的新实体。
- 在读到设备当前的控制字之前，集成拒绝下发任何控制，避免用默认值覆盖设备设置。
- 机智云接口只支持 TLS 1.2 + `AES128-SHA`，HA 默认的密码套件不含它，所以本集成的会话放宽了密码套件（**仍然校验证书**）。

## 协议备忘

<details>
<summary>展开</summary>

- 登录：`POST https://app.outes.com/app/smart_home/login/pwd`，请求体 `{"appKey": <AppID>, "data": {"account", "password", "lang"}, "version": "1.0"}`，响应 `data.userToken` 即机智云 user token
- 数据：`GET https://api.gizwits.com/app/devdata/{did}/latest`，头 `X-Gizwits-Application-Id` + `X-Gizwits-User-token`
- 控制：`POST https://api.gizwits.com/app/control/{did}`，`{"attrs": {"Ctrl_Set": "<16 字节 hex>"}}`
  - 字节 0：`05` 开 / `04` 关；字节 3：`01` 制冷 / `08` 制热
  - 字节 4–5：制冷目标水温 ×10（推断）；字节 6–7：制热目标水温 ×10（实测）；其余字节原样保留
- `Slv1_Sensor`：25 个大端 int16，各位含义见 `const.py` 里 `SLV1_KEYS` 的注释

</details>

## 反馈

提 issue 时请附上 设置 → 设备与服务 → 中广舒适家 → ⋮ → **下载诊断信息**（已自动脱敏）。**不要**贴原始抓包文件：里面有可以直接登录你账号的凭据。

## 许可

MIT
