# GW Instek GDM-8352 命令参考

本表是手册命令索引，而非 Skill 能力清单。`documented` 只表示手册有记录，不代表 `build_query` 可构建该命令。`Implemented` 由 `QUERY_SPECS` 与 `build_query` 的参数校验决定。`yes` 仅覆盖表中注明的允许形式，所有写命令和测量量程参数均被拒绝。

来源为 GW Instek《GDM-8352 使用手册》`82DM-83520E01` 中文版，文件位于 `ref/gwinstek/GDM-8352_User_Manual_82DM-83520E01.pdf`。命令表见 PDF pp. 99–106，命令参考见 PDF pp. 107–141。本文一律使用 **PDF 物理页**，手册印刷页码比它大 1。

`hardware-verified` 行共 8 条，证据均来自 2026-11-19 采集的同一台 GDM-8352，固件 `1.00`，序列号 `GEP848232`，USB CDC-ACM `2184:003b`。当日稍后已复测（`verify_all`，11:38:50Z）；证据目录 `artifacts/verification/evidence/20261119T113850Z/` 被 gitignore，仅作本地引用，不是必需依赖。证据仅覆盖观察到的确切命令和响应，不延伸至同族语法或可选参数。

方括号表示可选部分，竖线表示备选值，`<NR1>` 为整数，`<NRf>` 为灵活数字格式。表内的示例响应来自手册，真机接收内容另行注明。

## CONFigure

### 第一显示

| Command | Syntax | Parameters / return | PDF page | Evidence | Implemented |
|---|---|---|---|---|---|
| `CONF:VOLT:DC` | `CONFigure:VOLTage:DC [<NRf> \| MIN \| MAX \| DEF]` | 设置直流电压功能及可选量程。 | 107 | documented | no — refused by build_query |
| `CONF:VOLT:AC` | `CONFigure:VOLTage:AC [<NRf> \| MIN \| MAX \| DEF]` | 设置交流电压功能及可选量程。 | 107 | documented | no — refused by build_query |
| `CONF:VOLT:DCAC` | `CONFigure:VOLTage:DCAC [<NRf> \| MIN \| MAX \| DEF]` | 设置 DC+AC 电压功能及可选量程。 | 107 | documented | no — refused by build_query |
| `CONF:CURR:DC` | `CONFigure:CURRent:DC [<NRf> \| MIN \| MAX \| DEF]` | 设置直流电流功能及可选量程。 | 107 | documented | no — refused by build_query |
| `CONF:CURR:AC` | `CONFigure:CURRent:AC [<NRf> \| MIN \| MAX \| DEF]` | 设置交流电流功能及可选量程。 | 108 | documented | no — refused by build_query |
| `CONF:CURR:DCAC` | `CONFigure:CURRent:DCAC [<NRf> \| MIN \| MAX \| DEF]` | 设置 DC+AC 电流功能及可选量程。 | 108 | documented | no — refused by build_query |
| `CONF:RES` | `CONFigure:RESistance [<NRf> \| MIN \| MAX \| DEF]` | 设置二线电阻功能及可选量程。 | 108 | documented | no — refused by build_query |
| `CONF:FRES` | `CONFigure:FRESistance [<NRf> \| MIN \| MAX \| DEF]` | 设置四线电阻功能及可选量程。 | 108 | documented | no — refused by build_query |
| `CONF:FREQ` | `CONFigure:FREQuency [<NRf> \| MIN \| MAX \| DEF]` | 设置频率功能及可选量程。 | 109 | documented | no — refused by build_query |
| `CONF:PER` | `CONFigure:PERiod [<NRf> \| MIN \| MAX \| DEF]` | 设置周期功能及可选量程。 | 109 | documented | no — refused by build_query |
| `CONF:CONT` | `CONFigure:CONTinuity` | 无参数，设置通断功能。 | 109 | documented | no — refused by build_query |
| `CONF:DIOD` | `CONFigure:DIODe` | 无参数，设置二极管功能。 | 109 | documented | no — refused by build_query |
| `CONF:TEMP:TCO` | `CONFigure:TEMPerature:TCOuple [J \| K \| T]` | 设置热电偶测温功能，可选热电偶类型。 | 109 | documented | no — refused by build_query |
| `CONF:CAP` | `CONFigure:CAPacitance [<NRf> \| MIN \| MAX \| DEF]` | 设置电容功能及可选量程。 | 110 | documented | no — refused by build_query |
| `CONF:FUNC?` | `CONFigure:FUNCtion?` | 返回 `VOLT`、`VOLT:AC`、`VOLT:DCAC`、`CURR`、`CURR:AC`、`CURR:DCAC`、`RES`、`FRES`、`FREQ`、`PER`、`TEMP`、`DIOD`、`CONT` 或 `CAP`。 | 110 | documented | yes |
| `CONF:RANG?` | `CONFigure:RANGe?` | 返回当前功能的数值量程。手册列出 DCV `0.2, 2, 20, 200, 1000`；ACV `0.2, 2, 20, 200, 750`；DCI、ACI `0.02, 0.2, 1, 10`；RES、FRES `20E+1, 20E+2, 20E+3, 20E+4, 20E+5, 10E+6, 10E+7`；CAP `10E-9, 10E-8, 10E-7, 10E-6, 10E-5`。响应不携带功能或单位，单位 `UNVERIFIED`。 | 110 | documented | yes |
| `CONF:AUTO` | `CONFigure:AUTO ON \| OFF` | 设置第一显示自动量程开关。 | 110 | documented | no — refused by build_query |
| `CONF:AUTO?` | `CONFigure:AUTO?` | 返回 `0`（手动量程）或 `1`（自动量程）。 | 111 | documented | yes |

### 第二显示

| Command | Syntax | Parameters / return | PDF page | Evidence | Implemented |
|---|---|---|---|---|---|
| `CONF2:VOLT:DC` | `CONFigure2:VOLTage:DC [<NRf> \| MIN \| MAX \| DEF]` | 设置直流电压功能及可选量程。 | 112 | documented | no — refused by build_query |
| `CONF2:VOLT:AC` | `CONFigure2:VOLTage:AC [<NRf> \| MIN \| MAX \| DEF]` | 设置交流电压功能及可选量程。 | 112 | documented | no — refused by build_query |
| `CONF2:CURR:DC` | `CONFigure2:CURRent:DC [<NRf> \| MIN \| MAX \| DEF]` | 设置直流电流功能及可选量程。 | 112 | documented | no — refused by build_query |
| `CONF2:CURR:AC` | `CONFigure2:CURRent:AC [<NRf> \| MIN \| MAX \| DEF]` | 设置交流电流功能及可选量程。 | 112 | documented | no — refused by build_query |
| `CONF2:RES` | `CONFigure2:RESistance [<NRf> \| MIN \| MAX \| DEF]` | 设置二线电阻功能及可选量程。 | 113 | documented | no — refused by build_query |
| `CONF2:FRES` | `CONFigure2:FRESistance [<NRf> \| MIN \| MAX \| DEF]` | 设置四线电阻功能及可选量程。 | 113 | documented | no — refused by build_query |
| `CONF2:FREQ` | `CONFigure2:FREQuency [<NRf> \| MIN \| MAX \| DEF]` | 设置频率功能及可选量程。 | 113 | documented | no — refused by build_query |
| `CONF2:PER` | `CONFigure2:PERiod [<NRf> \| MIN \| MAX \| DEF]` | 设置周期功能及可选量程。 | 113 | documented | no — refused by build_query |
| `CONF2:OFF` | `CONFigure2:OFF` | 无参数，关闭第二显示功能。 | 114 | documented | no — refused by build_query |
| `CONF2:FUNC?` | `CONFigure2:FUNCtion?` | 返回 `VOLT`、`VOLT:AC`、`CURR`、`CURR:AC`、`RES`、`FRES`、`FREQ`、`PER` 或 `NON`。 | 114 | documented | no — refused by build_query |
| `CONF2:RANG?` | `CONFigure2:RANGe?` | 返回第二显示当前功能的数值量程；手册所列数值与 `CONF:RANG?` 条目相同，这不表示 `CONF2` 可设置其中每种功能。 | 114 | documented | no — refused by build_query |
| `CONF2:AUTO` | `CONFigure2:AUTO ON \| OFF` | 设置第二显示自动量程开关。 | 114 | documented | no — refused by build_query |
| `CONF2:AUTO?` | `CONFigure2:AUTO?` | 返回 `0`（手动量程）或 `1`（自动量程）。 | 115 | documented | no — refused by build_query |

## MEASure

### 第一显示

量程参数可能改变仪器设置。所有标 `yes` 的量程查询只构建无量程参数的形式。热电偶测温查询可选 `J`、`K` 或 `T` 类型参数。

| Command | Syntax | Parameters / return | PDF page | Evidence | Implemented |
|---|---|---|---|---|---|
| `MEAS:VOLT:DC?` | `MEASure:VOLTage:DC? [<NRf> \| MIN \| MAX \| DEF]` | 直流电压（V），手册响应例 `+0.10348E-01`。仅无参形式经真机验证。 | 116 | hardware-verified | yes |
| `MEAS:VOLT:AC?` | `MEASure:VOLTage:AC? [<NRf> \| MIN \| MAX \| DEF]` | 交流电压（V），响应例 `+0.09020E-01`。 | 116 | documented | yes |
| `MEAS:VOLT:DCAC?` | `MEASure:VOLTage:DCAC? [<NRf> \| MIN \| MAX \| DEF]` | DC+AC 电压（V），响应例 `+0.10123E-01`。 | 116 | documented | yes |
| `MEAS:CURR:DC?` | `MEASure:CURRent:DC? [<NRf> \| MIN \| MAX \| DEF]` | 直流电流（A），手册响应例 `+0.00703E-02`。仅无参形式经真机验证。 | 116 | hardware-verified | yes |
| `MEAS:CURR:AC?` | `MEASure:CURRent:AC? [<NRf> \| MIN \| MAX \| DEF]` | 交流电流（A），响应例 `+0.00872E-02`。 | 117 | documented | yes |
| `MEAS:CURR:DCAC?` | `MEASure:CURRent:DCAC? [<NRf> \| MIN \| MAX \| DEF]` | DC+AC 电流（A），响应例 `+0.01245E-02`。 | 117 | documented | yes |
| `MEAS:RES?` | `MEASure:RESistance? [<NRf> \| MIN \| MAX \| DEF]` | 二线电阻（Ω），响应例 `+1.00156E+03`。 | 117 | documented | yes |
| `MEAS:FRES?` | `MEASure:FRESistance? [<NRf> \| MIN \| MAX \| DEF]` | 四线电阻（Ω），响应例 `+1.11365E+03`。 | 117 | documented | yes |
| `MEAS:FREQ?` | `MEASure:FREQuency? [<NRf> \| MIN \| MAX \| DEF]` | 频率（Hz），响应例 `+1.00123E+03`。 | 118 | documented | yes |
| `MEAS:PER?` | `MEASure:PERiod? [MAX]` | 返回周期。手册只给出 `MAX` 参数用例，无参数枚举或响应示例。响应布局 `UNVERIFIED`。 | 118 | documented | yes |
| `MEAS:CONT?` | `MEASure:CONTinuity?` | 返回通断读数，手册无响应示例，布局 `UNVERIFIED`。 | 118 | documented | yes |
| `MEAS:DIOD?` | `MEASure:DIODe?` | 返回二极管读数，手册无响应示例，布局 `UNVERIFIED`。 | 118 | documented | yes |
| `MEAS:CAP?` | `MEASure:CAPacitance?` | 返回电容读数，手册无响应示例，布局 `UNVERIFIED`。 | 118 | documented | yes |
| `MEAS:TEMP:TCO?` | `MEASure:TEMPerature:TCOuple? [J \| K \| T]` | 返回选定热电偶的温度，响应例 `+0.02667E+03`，单位 `UNVERIFIED`。 | 119 | documented | yes |

### 第二显示

| Command | Syntax | Parameters / return | PDF page | Evidence | Implemented |
|---|---|---|---|---|---|
| `MEAS2:VOLT:DC?` | `MEASure2:VOLTage:DC? [<NRf> \| MIN \| MAX \| DEF]` | 直流电压，响应例 `+0.10321E-01`。 | 119 | documented | no — refused by build_query |
| `MEAS2:VOLT:AC?` | `MEASure2:VOLTage:AC? [<NRf> \| MIN \| MAX \| DEF]` | 交流电压，响应例 `+0.10020E-01`。 | 119 | documented | no — refused by build_query |
| `MEAS2:CURR:DC?` | `MEASure2:CURRent:DC? [<NRf> \| MIN \| MAX \| DEF]` | 直流电流，响应例 `+0.00856E-02`。 | 119 | documented | no — refused by build_query |
| `MEAS2:CURR:AC?` | `MEASure2:CURRent:AC? [<NRf> \| MIN \| MAX \| DEF]` | 交流电流，响应例 `+0.01254E-02`。 | 120 | documented | no — refused by build_query |
| `MEAS2:RES?` | `MEASure2:RESistance? [<NRf> \| MIN \| MAX \| DEF]` | 二线电阻，响应例 `+1.05203E+03`。 | 120 | documented | no — refused by build_query |
| `MEAS2:FRES?` | `MEASure2:FRESistance? [<NRf> \| MIN \| MAX \| DEF]` | 四线电阻，响应例 `+1.00023E+03`。 | 120 | documented | no — refused by build_query |
| `MEAS2:FREQ?` | `MEASure2:FREQuency? [<NRf> \| MIN \| MAX \| DEF]` | 频率，响应例 `+1.01122E+03`。 | 120 | documented | no — refused by build_query |
| `MEAS2:PER?` | `MEASure2:PERiod? [<NRf> \| MIN \| MAX \| DEF]` | 返回周期。手册示例为查询最大量程，无响应示例。 | 121 | documented | no — refused by build_query |

## SENSe

量程和自动量程参见 [CONFigure](#configure) 的 `RANGe?`、`AUTO`、`AUTO?`。本版手册的 `SENSe` 命令表与详解没有 `SENSe:RANGe`、`SENSe:AUTO` 或 `SENSe:FILTer` 条目。数字滤波使用 `AVERage`，阈值使用 `CONTinuity:THReshold`。

| Command | Syntax | Parameters / return | PDF page | Evidence | Implemented |
|---|---|---|---|---|---|
| `SENS:FUNC[1/2]` | `[SENSe:]FUNCtion[1/2] "<function>"` | 手册以 `1`、`2` 指示显示。第一显示可设 `VOLT[:DC]`、`VOLT:AC`、`VOLT:DCAC`、`CURR[:DC]`、`CURR:AC`、`CURR:DCAC`、`RES`、`FRES`、`FREQ`、`PER`、`TEMP:TCO`、`DIOD`、`CONT`、`CAP`。第二显示可设 `VOLT[:DC]`、`VOLT:AC`、`CURR[:DC]`、`CURR:AC`、`RES`、`FRES`、`FREQ`、`PER`、`NON`。 | 125 | documented | no — refused by build_query |
| `SENS:FUNC[1/2]?` | `[SENSe:]FUNCtion[1/2]?` | 返回对应显示的功能标记。与写入参数列表相比，返回的直流功能为 `VOLT`、`CURR`，热电偶功能为 `TEMP:TCO`。实测 `FUNC1?` 返回当前功能，观察到 `VOLT` 与 `CURR`；未留存原始字节。 | 125 | hardware-verified（仅 `FUNC1?`） | no — refused by build_query |
| `SENS:UNIT` | `[SENSe:]UNIT C \| F` | 温度单位设为摄氏或华氏。 | 124 | documented | no — refused by build_query |
| `SENS:UNIT?` | `[SENSe:]UNIT?` | 返回当前温度单位，命令详解未列响应字面格式。`UNIT?` 亦为手册列出的有效形式。 | 124（语法别名见 97） | documented | yes |
| `SENS:DET:RATE` | `[SENSe:]DETector:RATE S \| M \| F` | 设置慢、中、快三档采样率。 | 122 | documented | no — refused by build_query |
| `SENS:DET:RATE?` | `[SENSe:]DETector:RATE?` | 返回 `SLOW`、`MID` 或 `FAST`。 | 122 | documented | no — refused by build_query |
| `SENS:AVER:TCON` | `[SENSe:]AVERage:TCONtrol MOV \| REP` | 选择移动平均或重复平均数字滤波。 | 122 | documented | no — refused by build_query |
| `SENS:AVER:TCON?` | `[SENSe:]AVERage:TCONtrol?` | 返回 `MOV` 或 `REP`。 | 122 | documented | no — refused by build_query |
| `SENS:AVER:COUN` | `[SENSe:]AVERage:COUNt <NR1> \| MIN \| MAX` | 设置滤波平均次数，整数范围 2–320。 | 122 | documented | no — refused by build_query |
| `SENS:AVER:COUN?` | `[SENSe:]AVERage:COUNt?` | 返回整数，手册列 `+002` 至 `+320`。 | 122 | documented | no — refused by build_query |
| `SENS:AVER:WIND` | `[SENSe:]AVERage:WINDow 0.01 \| 0.1 \| 1 \| 10 \| 0` | 设置百分比滤波窗口，`0` 表示无窗口。 | 123 | documented | no — refused by build_query |
| `SENS:AVER:WIND?` | `[SENSe:]AVERage:WINDow?` | 返回 `0.01`、`0.1`、`1`、`10` 或 `NONE`。 | 123 | documented | no — refused by build_query |
| `SENS:AVER:STAT` | `[SENSe:]AVERage:STATe ON \| OFF` | 设置数字滤波开关。 | 123 | documented | no — refused by build_query |
| `SENS:AVER:STAT?` | `[SENSe:]AVERage:STATe?` | 返回 `0`（关闭）或 `1`（开启）。 | 123 | documented | no — refused by build_query |
| `SENS:CONT:THR` | `[SENSe:]CONTinuity:THReshold <NRf>` | 设置通断阈值，范围 0–2000 Ω。 | 124 | documented | no — refused by build_query |
| `SENS:CONT:THR?` | `[SENSe:]CONTinuity:THReshold?` | 返回通断阈值，手册列为 `<NR1>`，范围 0–2000。 | 124 | documented | no — refused by build_query |
| `SENS:TEMP:TCO:TYPE` | `[SENSe:]TEMPerature:TCOuple:TYPE J \| K \| T` | 设置热电偶类型；类型的读写形式请用本命令，`CONF:TEMP:TCO` 只在设置测量功能时附带类型。 | 121 | documented | no — refused by build_query |
| `SENS:TEMP:TCO:TYPE?` | `[SENSe:]TEMPerature:TCOuple:TYPE?` | 返回热电偶类型：`J`、`K` 或 `T`。 | 121 | documented | no — refused by build_query |
| `SENS:FREQ:INP` | `[SENSe:]FREQuency:INPutjack (0 \| 1 \| 2)` | 指定频率测量的输入端子：`0`=VOLT、`1`=1A、`2`=10A。 | 123 | documented | no — refused by build_query |
| `SENS:FREQ:INP?` | `[SENSe:]FREQuency:INPutjack?` | 返回频率测量所用的输入端子：`VOLT`、`1A` 或 `10A`。 | 123 | documented | no — refused by build_query |
| `SENS:PER:INP` | `[SENSe:]PERiod:INPutjack (0 \| 1 \| 2)` | 指定周期测量的输入端子：`0`=VOLT、`1`=1A、`2`=10A。 | 124 | documented | no — refused by build_query |
| `SENS:PER:INP?` | `[SENSe:]PERiod:INPutjack?` | 返回周期测量所用的输入端子：`VOLT`、`1A` 或 `10A`。 | 124 | documented | no — refused by build_query |

## CALCulate

| Command | Syntax | Parameters / return | PDF page | Evidence | Implemented |
|---|---|---|---|---|---|
| `CALC:FUNC` | `CALCulate:FUNCtion OFF \| MIN \| MAX \| HOLD \| REL \| COMP \| DB \| DBM \| MXB \| INV \| REF` | 设置高级计算功能。 | 126 | documented | no — refused by build_query |
| `CALC:FUNC?` | `CALCulate:FUNCtion?` | 返回当前高级计算功能，手册未列响应字面格式。 | 126 | documented | no — refused by build_query |
| `CALC:STAT` | `CALCulate:STATe ON \| OFF` | 启用或禁用高级计算功能。 | 126 | documented | no — refused by build_query |
| `CALC:STAT?` | `CALCulate:STATe?` | 返回 `0`（关闭）或 `1`（开启）。 | 126 | documented | no — refused by build_query |
| `CALC:MIN?` | `CALCulate:MINimum?` | 返回最大/最小值测量的最小值，手册未列响应格式。 | 126 | documented | no — refused by build_query |
| `CALC:MAX?` | `CALCulate:MAXimum?` | 返回最大/最小值测量的最大值，手册未列响应格式。 | 126 | documented | no — refused by build_query |
| `CALC:HOLD:REF` | `CALCulate:HOLD:REFerence <NRf>` | 设置保持功能阈值，可用值为 `0.01`、`0.1`、`1`、`10`（%）。 | 127 | documented | no — refused by build_query |
| `CALC:HOLD:REF?` | `CALCulate:HOLD:REFerence?` | 返回保持功能的百分比阈值，手册未列响应格式。 | 127 | documented | no — refused by build_query |
| `CALC:REL:REF` | `CALCulate:REL:REFerence <NRf> \| MIN \| MAX` | 设置相对测量参考值。 | 127 | documented | no — refused by build_query |
| `CALC:REL:REF?` | `CALCulate:REL:REFerence?` | 返回相对测量参考值，手册未列响应格式。 | 127 | documented | no — refused by build_query |
| `CALC:LIM:LOW` | `CALCulate:LIMit:LOWer <NRf> \| MIN \| MAX` | 设置比较功能下限。 | 127 | documented | no — refused by build_query |
| `CALC:LIM:LOW?` | `CALCulate:LIMit:LOWer?` | 返回比较功能下限，手册未列响应格式。 | 127 | documented | no — refused by build_query |
| `CALC:LIM:UPP` | `CALCulate:LIMit:UPPer <NRf> \| MIN \| MAX` | 设置比较功能上限。 | 128 | documented | no — refused by build_query |
| `CALC:LIM:UPP?` | `CALCulate:LIMit:UPPer?` | 返回比较功能上限，手册未列响应格式。 | 128 | documented | no — refused by build_query |
| `CALC:DB:REF` | `CALCulate:DB:REFerence <NRf> \| MIN \| MAX` | 设置 dB 功能参考电压。 | 128 | documented | no — refused by build_query |
| `CALC:DB:REF?` | `CALCulate:DB:REFerence?` | 返回 dB 功能参考电压，手册未列响应格式。 | 128 | documented | no — refused by build_query |
| `CALC:DBM:REF` | `CALCulate:DBM:REFerence <NRf> \| MIN \| MAX` | 设置 dBm 功能参考电阻。 | 128 | documented | no — refused by build_query |
| `CALC:DBM:REF?` | `CALCulate:DBM:REFerence?` | 返回 dBm 功能参考电阻，手册未列响应格式。 | 128 | documented | no — refused by build_query |
| `CALC:MATH:MMF` | `CALCulate:MATH:MMFactor <NRf> \| MIN \| MAX` | 设置比例系数 M。 | 129 | documented | no — refused by build_query |
| `CALC:MATH:MMF?` | `CALCulate:MATH:MMFactor?` | 返回比例系数 M，手册未列响应格式。 | 129 | documented | no — refused by build_query |
| `CALC:MATH:MBF` | `CALCulate:MATH:MBFactor <NRf> \| MIN \| MAX` | 设置偏移系数 B。 | 129 | documented | no — refused by build_query |
| `CALC:MATH:MBF?` | `CALCulate:MATH:MBFactor?` | 返回偏移系数 B，手册未列响应格式。 | 129 | documented | no — refused by build_query |
| `CALC:MATH:PERC` | `CALCulate:MATH:PERCent <NRf> \| MIN \| MAX` | 设置百分比功能参考值。 | 129 | documented | no — refused by build_query |
| `CALC:MATH:PERC?` | `CALCulate:MATH:PERCent?` | 返回百分比功能参考值，手册未列响应格式。 | 129 | documented | no — refused by build_query |

## TRIGger

| Command | Syntax | Parameters / return | PDF page | Evidence | Implemented |
|---|---|---|---|---|---|
| `READ?` | `READ?` | 返回第一、第二显示值。手册多样本示例为逗号分隔的成对字段，真机此次返回一对。第二字段的功能及单位 `UNVERIFIED`。 | 130 | hardware-verified | yes |
| `VAL1?` | `VAL1?` | 返回第一显示的读数。手册示例为三个逗号分隔的科学计数法字段。 | 130 | documented | no — refused by build_query |
| `VAL2?` | `VAL2?` | 返回第二显示的读数。手册示例为三个逗号分隔的科学计数法字段。 | 131 | documented | no — refused by build_query |
| `TRIG:SOUR` | `TRIGger:SOURce INT \| EXT` | 选择内部或外部触发源。 | 131 | documented | no — refused by build_query |
| `TRIG:SOUR?` | `TRIGger:SOURce?` | 返回当前触发源，手册未列响应字面格式。 | 131 | documented | no — refused by build_query |
| `TRIG:AUTO` | `TRIGger:AUTO ON \| OFF` | 设置自动触发模式。 | 131 | documented | no — refused by build_query |
| `TRIG:AUTO?` | `TRIGger:AUTO?` | 返回 `0`（关闭）或 `1`（开启）。 | 131 | documented | no — refused by build_query |
| `TRIG:COUN` | `TRIGger:COUNt <NR1> \| MIN \| MAX` | 设置触发计数，整数范围 1–9999。 | 132 | documented | no — refused by build_query |
| `TRIG:COUN?` | `TRIGger:COUNt? [MIN \| MAX]` | 返回触发计数，手册未列响应字面格式。 | 132 | documented | no — refused by build_query |

## SAMPle

| Command | Syntax | Parameters / return | PDF page | Evidence | Implemented |
|---|---|---|---|---|---|
| `SAMP:COUN` | `SAMPle:COUNt <NR1> \| MIN \| MAX` | 设置样本数，手册列出的整数范围为 USB-CDC 1–9999、USB-TMC 1–320。 | 132 | documented | no — refused by build_query |
| `SAMP:COUN?` | `SAMPle:COUNt? [MIN \| MAX]` | 返回样本数，手册未列响应字面格式。 | 132 | documented | no — refused by build_query |

## SYSTem

| Command | Syntax | Parameters / return | PDF page | Evidence | Implemented |
|---|---|---|---|---|---|
| `SYST:BEEP:STAT` | `SYSTem:BEEPer:STATe <NR1>` | 手册仅列 `0`（不响）、`1`（通过时响）、`2`（失败时响）。 | 133 | documented | no — refused by build_query |
| `SYST:BEEP:STAT 0` / `SYST:BEEP:STAT OFF` | `SYST:BEEP:STAT 0` 或 `SYST:BEEP:STAT OFF` | 两种写法均被静默接受、无响应。发送 `SYST:BEEP:STAT 0` 后回读仍为 `No Beep`，蜂鸣确已关闭；状态由后续查询确立，静默本身不能证实。手册只列数值参数 `0`/`1`/`2`，未列 `OFF`。 | —（同族 133） | hardware-verified | no — refused by build_query |
| `SYST:BEEP:STAT?` | `SYSTem:BEEPer:STATe?` | 手册列 `No Beep`、`Beep on Pass`、`Beep on Fail`；真机仅观察到 `No Beep`。 | 133 | hardware-verified | yes |
| `SYST:BEEP:ERR` | `SYSTem:BEEPer:ERRor ON \| OFF` | 设置 SCPI 出错时蜂鸣开关。 | 133 | documented | no — refused by build_query |
| `SYST:BEEP:ERR?` | `SYSTem:BEEPer:ERRor?` | 返回 `0`（关闭）或 `1`（开启）。 | 133 | documented | no — refused by build_query |
| `SYST:ERR?` | `SYSTem:ERRor?` | 手册说明返回当前系统错误（若有），未定义格式。真机返回自由文本 `Command error`。 | 133 | hardware-verified | yes |
| `SYST:BEEP` | `SYSTem:BEEPer` | 无参数，发出一次蜂鸣。手册未给出返回或副作用说明。 | 133 | documented | no — refused by build_query |
| `SYST:VERS?` | `SYSTem:VERSion?` | 返回系统版本，格式 `X.XX.`（手册原文带句点）。 | 134 | documented | no — refused by build_query |
| `SYST:DISP` | `SYSTem:DISPlay ON \| OFF` | 关闭或打开前面板显示。 | 134 | documented | no — refused by build_query |
| `SYST:DISP?` | `SYSTem:DISPlay?` | 返回显示状态，`0`=关闭、`1`=打开。 | 134 | documented | no — refused by build_query |
| `SYST:SER?` | `SYSTem:SERial?` | 返回九个字符的序列号。手册未给响应示例，字段布局 `UNVERIFIED`。 | 134 | documented | no — refused by build_query |
| `INP:IMP:AUTO` | `INPut:IMPedance:AUTO ON \| OFF` | 设置 DCV 模式（100 mV 与 1 V 量程）的输入阻抗：`ON`=10 GΩ、`OFF`=10 MΩ。 | 134 | documented | no — refused by build_query |
| `INP:IMP:AUTO?` | `INPut:IMPedance:AUTO?` | 返回输入阻抗模式，`0`=OFF(10 MΩ)、`1`=ON(10 GΩ)。 | 134 | documented | no — refused by build_query |
| `DISP:TEXT` | `DISPlay:TEXT "<string>"` | 在显示区写一条消息：字母数字加空格、`+`、`-`、`/`，最多 13 个字符。 | 135 | documented | no — refused by build_query |
| `DISP:TEXT?` | `DISPlay:TEXT?` | 返回当前显示的消息。手册未列响应格式。 | 135 | documented | no — refused by build_query |
| `DISP:TEXT:CLE` | `DISPlay:TEXT:CLEar` | 无参数，清除显示消息。 | 135 | documented | no — refused by build_query |
| `DIG:MODE` | `DIGitalio:MODE NORM \| USER` | 设置 Digital I/O 口的模式；`USER` 模式下才可用 `DIGitalio[1\|2\|3\|4]:SETup`。 | 135 | documented | no — refused by build_query |
| `DIG:MODE?` | `DIGitalio:MODE?` | 返回 Digital I/O 模式：`NORM` 或 `USER`。 | 135 | documented | no — refused by build_query |
| `DIG[1\|2\|3\|4]:SET` | `DIGitalio[1\|2\|3\|4]:SETup ON \| OFF` | 在 `USER` 模式下设置所选引脚（1–4）的状态。 | 136 | documented | no — refused by build_query |
| `DIG[1\|2\|3\|4]:SET?` | `DIGitalio[1\|2\|3\|4]:SETup?` | 返回所选引脚状态，`0`=OFF、`1`=ON。 | 136 | documented | no — refused by build_query |
| `DIG0:SET` | `DIGitalio0:SETup <boolean>,<boolean>,<boolean>,<boolean>` | 在 `USER` 模式下一次设置四个引脚（CH1–CH4），`0`=OFF、`1`=ON。这一条只出现在命令详解（PDF p. 136），指令表（PDF pp. 99–106）未列。 | 136 | documented | no — refused by build_query |
| `DIG0:SET?` | `DIGitalio0:SETup?` | 返回四个逗号分隔的布尔值，对应四个引脚。同样只出现在命令详解。 | 136 | documented | no — refused by build_query |
| `STAT:QUES:ENAB` | `STATus:QUEStionable:ENABle` | 设置 Questionable Data Enable 寄存器。手册未列参数或范围。 | 137 | documented | no — refused by build_query |
| `STAT:QUES:ENAB?` | `STATus:QUEStionable:ENABle?` | 返回 Questionable Data Enable 寄存器内容。 | 137 | documented | no — refused by build_query |
| `STAT:QUES:EVEN?` | `STATus:QUEStionable:EVENt?` | 返回 Questionable Data Event 寄存器内容。 | 137 | documented | no — refused by build_query |
| `STAT:PRES` | `STATus:PRESet` | 无参数，清除 Questionable Data Enable 寄存器。 | 137 | documented | no — refused by build_query |
| `SYST:LOC` | `SYSTem:LOCal` | 启用前面板控制并关闭远程控制。 | 137 | documented | no — refused by build_query |
| `SYST:REM` | `SYSTem:REMote` | 启用远程控制并关闭前面板控制；按 `2ND` 或 local 键可回到本地。 | 137 | documented | no — refused by build_query |
| `SYST:RWL` | `SYSTem:RWLock` | 锁定前面板：此后面板键不再能回到本地，只能用 `SYSTem:LOCal` 解锁。 | 138 | documented | no — refused by build_query |

## IEEE 488.2 公共命令

| Command | Syntax | Parameters / return | PDF page | Evidence | Implemented |
|---|---|---|---|---|---|
| `*IDN?` | `*IDN?` | 四个逗号分隔字段，依次为厂商、型号、序列号、系统版本。手册响应例 `GWInstek,GDM8352,00000000,1.0`。 | 139 | hardware-verified | yes |
| `*RST` | `*RST` | 恢复默认面板设置。 | 139 | documented | no — refused by build_query |
| `*CLS` | `*CLS` | 清除事件状态，手册列出输出队列、操作事件、可疑事件、标准事件状态。 | 138 | documented | no — refused by build_query |
| `*ESE` | `*ESE <NR1>` | 设置事件状态使能寄存器，整数范围 0–255。 | 138 | documented | no — refused by build_query |
| `*ESE?` | `*ESE?` | 返回事件状态使能寄存器内容，响应例 `130`。 | 138 | documented | no — refused by build_query |
| `*ESR?` | `*ESR?` | 返回标准事件状态寄存器内容，响应例 `198`。 | 139 | documented | no — refused by build_query |
| `*OPC` | `*OPC` | 待操作全部完成后设置标准事件状态寄存器的操作完成位（bit 0）。 | 139 | documented | no — refused by build_query |
| `*OPC?` | `*OPC?` | 待操作全部完成后在输出队列放入 `1`。 | 139 | documented | no — refused by build_query |
| `*SRE` | `*SRE <NR1>` | 设置服务请求使能寄存器，整数范围 0–255。 | 140 | documented | no — refused by build_query |
| `*SRE?` | `*SRE?` | 返回服务请求使能寄存器内容，手册未列响应示例。 | 140 | documented | no — refused by build_query |
| `*STB?` | `*STB?` | 返回状态字节寄存器内容，响应例 `64`。 | 140 | documented | no — refused by build_query |
| `*TRG` | `*TRG` | 手动触发 DMM。 | 140 | documented | no — refused by build_query |
| `*PSC` | `*PSC <Boolean>` | 清除 Power On 状态：`0`=不清除、`1`=清除。 | 139 | documented | no — refused by build_query |
| `*PSC?` | `*PSC?` | 返回 Power On Clear 状态，`0`=不清除、`1`=清除。 | 139 | documented | no — refused by build_query |

手册公共命令表（PDF p. 106）及详解（PDF pp. 138–141）无 `*TST?` 或 `*WAI` 条目。两者均被 `build_query` 拒绝，语法、参数、响应及适用性无此手册依据。

## 五项真机观察

1. **`CONF?` 无响应。** 本次采集在超时前未收到字节。手册没有裸 `CONF?`，正确查询为 `CONF:FUNC?`（功能，PDF p. 110）、`CONF:RANG?`（量程，p. 110）及 `CONF:AUTO?`（自动量程状态，p. 111）。这三条均为 `documented`。
2. **`SYST:ERR?` 返回自由文本。** 原文为 `Command error`。手册只说返回当前系统错误（若有，PDF p. 133），未定义错误编号或错误队列。此响应不应作为错误队列条目解析。
3. **`SYST:BEEP:STAT?` 的返回为三态文本。** 手册列出 `No Beep`、`Beep on Pass`、`Beep on Fail`（PDF p. 133），夹具仅记录 `No Beep`。`0`、`1`、`2` 属于同族写命令参数，不能用于解释查询响应。`SYST:BEEP:STAT 0` 与 `SYST:BEEP:STAT OFF` 均被静默接受、无响应；发送 `0` 后回读仍为 `No Beep`，蜂鸣确已关闭，状态由后续查询确立，静默本身不能证实。
4. **`READ?` 本次返回两个逗号分隔字段。** 响应正文为 `+0.00023E-02,+0.00000E+00`。手册按第一、第二显示顺序给出值（PDF p. 130），多样本示例含多对字段。本次第二字段的功能和单位均为 `UNVERIFIED`，即使数值等于零也不能据此推断其含义。
5. **`FUNC1?` 返回当前功能。** 实测观察到 `VOLT` 与 `CURR` 两种值；未留存原始字节。手册对应查询为 `[SENSe:]FUNCtion[1/2]?`（PDF p. 125），其他功能标记仍为 `documented`，本 Skill 不实现该查询。
