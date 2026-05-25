# RIGOL DG1022Z 上位机

这是一个用于控制 RIGOL DG1022Z/DG1000Z 系列函数/任意波形发生器的 PySide6 上位机。

## 功能

- VISA 地址连接、断开、资源刷新、`*IDN?` 查询
- CH1/CH2 独立参数设置
- 波形类型选择，支持正弦、方波、脉冲、斜波、噪声、DC、USER 以及可编辑的内建任意波形 SCPI 名称
- 频率或周期设置
- 幅度/偏置或高电平/低电平设置
- 占空比、相位、脉宽、斜波对称性设置
- Burst 模式设置：N 周期、无限、门控，触发源、周期数、内部触发周期、延时、极性等
- 输出通道、输出开关、负载阻抗选择
- 软件触发、相位同步、系统错误查询

## 安装

建议在 Python 3.10+ 环境中安装：

```powershell
python -m pip install -r requirements.txt
```

如果没有 NI-VISA，可以先安装 `pyvisa-py` 并通过 LAN/USB 使用纯 Python 后端；程序会先尝试系统默认 VISA 后端，失败后自动回退到 `@py`。

## 运行

```powershell
python main.py
```

常见 VISA 地址示例：

- LAN: `TCPIP::192.168.1.191::INSTR`
- USB: `USB0::0x1AB1::0x0642::DG1ZA000000000::INSTR`

## 无硬件测试

核心 SCPI 生成逻辑不依赖 PyVISA 或 PySide6：

```powershell
python -m unittest discover -s tests
```

## 结构

- `src/rigol_dg1022z/domain.py`：领域模型与参数校验
- `src/rigol_dg1022z/scpi.py`：DG1022Z SCPI 命令生成
- `src/rigol_dg1022z/visa.py`：PyVISA 适配器
- `src/rigol_dg1022z/app.py`：PySide6 界面
- `tests/`：无硬件单元测试
