"""Constants for the Zhongguang Gizwits integration."""

DOMAIN = "zhongguang_gizwits"
# 机智云服务端只接受 TLS1.2 + AES128-SHA（无前向保密的老套件），HA 默认密码套件
# 不包含它，所以会话用 SSLCipherList.INSECURE（仍校验证书，只放宽套件）。
API_BASE = "https://api.gizwits.com"
DEFAULT_SCAN_INTERVAL = 10
MANUFACTURER = "中广欧特斯 (Gizwits)"

CONF_APP_ID = "app_id"
CONF_TOKEN = "token"
CONF_DID = "did"
CONF_PRODUCT_KEY = "product_key"
CONF_ACCOUNT = "account"            # 手机号，规范成 +86XXXXXXXXXXX
CONF_PASSWORD = "password"          # 明文密码（encrypt=False）或 App 抓到的密文（encrypt=True）
CONF_ENCRYPTED = "encrypted"

# 中广 App（机智云「超级 App」RN 网关）自己的登录服务器。App 用 http，这里走 https（证书校验正常）。
# POST /app/smart_home/login/pwd  信封 {"appKey": appid, "data": {...}, "version": "1.0"}
#   data.userToken 就是 api.gizwits.com 的 X-Gizwits-User-token；token 有效期内重复登录返回同一个 token
OUTES_API = "https://app.outes.com"
OUTES_LOGIN_PATH = "/app/smart_home/login/pwd"
DEFAULT_APP_ID = "37931b372b4f402f87038c9c1844e7f8"   # 中广 App 的机智云 AppID（公开值，不是密钥）
# 网关业务码（字符串）：1000033 账号或者密码错误，1000000 用户不存在 → 凭据问题，绝不重试（防锁号）
OUTES_BAD_CREDENTIAL_CODES = {"1000033", "1000000"}
RELOGIN_COOLDOWN = 300              # 两次自动登录至少间隔 5 分钟

# 机智云业务错误码（HTTP 400 + error_code），token 失效是 9004，不是 401/403
GIZ_AUTH_ERROR_CODES = {9004, 9005, 9006}

# Ctrl_Set layout:
#   [0]     0x04 = off, 0x05 = on                      （现场实测）
#   [3]     0x01 = cool, 0x08 = heat                   （现场实测）
#   [4:6]   制冷目标水温, big endian, degC * 10         （推断：作者机器上值为 10.0，与末端控制器的供冷目标一致；未实写验证）
#   [6:8]   制热目标水温, big endian, degC * 10         （现场实测 30→29→30）
CTRL_TEMPLATE = "05000008006400dc1122000000640000"   # 仅作长度/格式参考；没读到真实 Ctrl_Set 前拒绝下发

# 字段解码只在这个 product_key 上对照过线控器面板（其他型号可能不同）
VERIFIED_PRODUCT_KEYS = {"fb80943e1165424baab2529ca3bdc2ac"}

HVAC_MODE_TO_BYTE = {"cool": 0x01, "heat": 0x08}
BYTE_TO_HVAC_MODE = {v: k for k, v in HVAC_MODE_TO_BYTE.items()}
SETPOINT_OFFSET = {"cool": 4, "heat": 6}

# 目标出水温度可写范围。外机极端天气下会用到：制热最高 55 °C、制冷最低 7 °C（用户按线控器给出）。
# 制热下限 16、制冷上限 25 沿用旧值，未对照线控器。设备里按 ×10 存，但只实写验证过整数，所以步进取 1。
SETPOINT_RANGE = {"heat": (16.0, 55.0), "cool": (7.0, 25.0)}
SETPOINT_STEP = 1.0

# 原始字段里体积大且全零/无意义的，不放进实体属性（避免 recorder 膨胀）
RAW_ATTR_SKIP = {"Time_Set", "OTA_FlashMsg", "Update_Ctrl"}

# 传感器定义: (key, name, scale, kind, enabled_default)
#   scale: 原始 int16 乘以该系数
#   kind:  "temp" | "freq" | "volt" | "raw"
# Mst_Temp: 6 x int16 big endian
MST_TEMP_KEYS = [
    ("outlet_water_temp", "出水温度", 0.1, "temp", True),
    ("inlet_water_temp", "回水温度", 0.1, "temp", True),
    ("mst_temp_3", "主机温度3", 0.1, "temp", False),
    ("mst_temp_4", "主机温度4", 0.1, "temp", False),
    ("ambient_temp", "室外环境温度", 0.1, "temp", True),
    ("mst_temp_6", "主机温度6", 0.1, "temp", True),
]

# Slv1_Sensor: 25 x int16 big endian。
# 2026-11-03 晚用线控器「1号机组状态」面板照片逐项对照（停机后约 6 分钟的快照几乎逐位相等）。
# 面板沿用制冷工况的叫法：「蒸发温度」在制热时其实是板换（冷凝）侧温度。
# key 保持 v0.1.0 的不变（unique_id 不变，历史保留），只改名称/系数/单位。
SLV1_KEYS = [
    ("slv1_ambient", "翅片温度", 0.1, "temp", True),            # [0] 面板 16.2
    ("slv1_suction", "蒸发温度（板换）", 0.1, "temp", True),     # [1] 面板 25.0
    ("slv1_coil", "吸气温度", 0.1, "temp", True),               # [2] 面板 18.4
    ("slv1_discharge", "排气温度", 0.1, "temp", True),          # [3] 面板 39.2
    ("slv1_outdoor", "从机1 未知温度4", 0.1, "temp", False),     # [4] 恒 -7.7，面板无对应
    ("slv1_outlet_water", "从机1 出水温度", 0.1, "temp", True),   # [5]
    ("slv1_inlet_water", "从机1 回水温度", 0.1, "temp", True),    # [6]
    ("slv1_s7", "从机1 模拟量7", 1, "raw", False),
    ("slv1_s8", "从机1 模拟量8", 1, "raw", False),
    ("slv1_room", "从机1 室外环境温度", 0.1, "temp", True),       # [9] = Mst 环境温度
    ("slv1_s10", "从机1 模拟量10", 1, "raw", False),
    ("slv1_s11", "从机1 模拟量11", 1, "raw", False),
    ("slv1_s12", "排气饱和温度", 0.1, "temp", True),            # [12] 面板 16.9
    ("slv1_s13", "排气压力", 0.01, "pressure", True),          # [13] 面板 12.3 bar
    ("slv1_s14", "AC 输入电压", 1, "volt", True),               # [14] 面板 220
    ("slv1_s15", "压缩机频率", 1, "freq", True),                # [15]
    ("slv1_s16", "直流风机1#", 1, "raw", True),                # [16] 运行 59–70，单位未知
    ("slv1_s17", "母线电压", 1, "volt", True),                  # [17] 面板 314
    ("slv1_s18", "IPM 温度", 1, "temp", True),                  # [18] 面板 50.0（运行时也恒 50）
    ("slv1_s19", "从机1 模拟量19", 1, "raw", False),             # 恒 0（可能是直流风机2#）
    ("slv1_s20", "PFC 温度", 1, "temp", False),                 # [20] 面板 -55.0（恒定，像未接探头）
    ("slv1_s21", "从机1 模拟量21", 1, "raw", False),             # 21–24 运行时也恒 0；面板上的
    ("slv1_s22", "从机1 模拟量22", 1, "raw", False),             # 压机相电流/AC输入电流/输出电压/
    ("slv1_s23", "从机1 模拟量23", 1, "raw", False),             # 直流水泵开度 未在云端看到非零值
    ("slv1_s24", "从机1 模拟量24", 1, "raw", False),
]

# 派生 / 其他字段
DISCHARGE_SUPERHEAT_KEY = "discharge_superheat"   # 排气温度 − 排气饱和温度（面板「排气过热度」同算法）
PANEL_ROOM_KEY = "panel_room_temp"                 # Reserve_ReadSLow[0:2] ×0.1，线控器「室内温度」

COMPRESSOR_FREQ_KEY = "slv1_s15"

# Slv1_C1_ExvSteb: 6 x int16；idx2 = 制热阀 EXV1 步数（面板对照确认）
EXV_KEYS = [
    ("slv1_exv_steps", "制热阀 EXV1", 2),   # 面板 300（运行 276–278）
]

# Slv1_C1_Bit_States 字节0 bit2：压缩机运行位。11-03 运行时线控器第3页亮 压缩机/驱动器/PFC/稳频/水泵，
# 云端只有这一位（待机水泵亮时它为0）→ 云端不镜像第3页，这位随压缩机组一起开关；变化即报，是最准的启停沿
RUN_REQUEST_BYTE = 0
RUN_REQUEST_MASK = 0x04
