# KyokuEventTuple V2 协议

参考来源：[MJAI protocol](https://riichi.dev/docs/protocol)

## 1. 背景与目标

本文档定义一种面向 Transformer encoder 的麻将局面输入协议。协议把当前可见状态和已经发生的真实事件编码为定长离散整数元组序列。

协议目标：

| 目标 | 说明 |
|---|---|
| 定长离散元组 | 每个 token 都是固定维度整数 tuple |
| 状态 + 事件 | 输入同时包含当前状态快照和本局事件历史 |
| 贴近 MJAI | 事件类型参考 `tsumo`、`dahai`、`chi`、`pon`、`kan`、`reach` 等局内事件 |
| 只记录事实 | 事件序列只记录已经发生并被服务器确认的局内事件 |
| 环境处理生命周期 | `start_game`、`start_kyoku`、`end_kyoku`、`end_game` 用于环境初始化、重置和结算，不进入模型事件序列 |
| 环境处理决策 | `request_action`、`possible_actions`、`action_ack` 不进入事件序列 |
| 相对视角 | 玩家全部使用当前模型视角的相对座位 |

## 2. Token 结构

每个 token 固定由九个整数维度组成：

```text
token = (TYPE, ACTOR, TARGET, TILE, TILE2, TILE3, VALUE, FLAG, STEP)
```

| 维度 | Key | 中文名 | 含义 |
|---|---|---|---|
| 第1维 | `TYPE` | 语义类型 | 当前 token 是哪类状态、事件或特殊标记 |
| 第2维 | `ACTOR` | 主体 | 状态所属玩家或事件执行者 |
| 第3维 | `TARGET` | 来源/目标 | 鸣牌来源、放铳者、目标玩家等 |
| 第4维 | `TILE` | 主牌 | 事件或状态涉及的主要牌 |
| 第5维 | `TILE2` | 关联牌1 | 吃碰杠 consumed 牌、状态补充牌，或 `NONE` |
| 第6维 | `TILE3` | 关联牌2 | 吃碰杠 consumed 牌、状态补充牌，或 `NONE` |
| 第7维 | `VALUE` | 数值 | 通用小数值桶；未使用时填 `VALUE_NONE` |
| 第8维 | `FLAG` | 标志 | 少量全局标志，例如摸切、手切、荣和/自摸、吃牌形态、公开/闭合 |
| 第9维 | `STEP` | 时间位置 | 巡目时间桶 |

示例：

```text
(EVENT_CHI, SELF, KAMICHA, 5p, 4p, 6p, VALUE_NONE, CHI_MID, STEP_6)
```

落成整数后类似：

```text
(19, 1, 4, 14, 13, 15, 0, 18, 6)
```

## 3. 输入序列结构

推荐的 encoder 输入序列结构为：

```text
[STATE tokens...]
[SEP]
[EVENT history tokens...]
```

模型侧可以在协议序列后追加内部 `DECISION` embedding 作为聚合位置，但 `DECISION` 不占用本协议的 `TYPE` 枚举。

MJAI 的 `request_action`、`possible_actions` 和 `action_ack` 不进入本协议事件序列。合法动作集合应由环境侧 action mask、候选动作列表或监督标签处理。

## 4. 维度取值范围

| 维度 | Key | 最小值 | 最大值 | 词表大小 | 说明 |
|---|---|---:|---:|---:|---|
| 第1维 | `TYPE` | 0 | 35 | 36 | 状态、事件、特殊 token 和 5 个预留枚举 |
| 第2维 | `ACTOR` | 0 | 4 | 5 | 相对座位 |
| 第3维 | `TARGET` | 0 | 4 | 5 | 与 `ACTOR` 同一套相对座位 |
| 第4维 | `TILE` | 0 | 38 | 39 | MJAI 风格牌名，含 `NONE` 和 `UNKNOWN` |
| 第5维 | `TILE2` | 0 | 38 | 39 | 与 `TILE` 同一套枚举 |
| 第6维 | `TILE3` | 0 | 38 | 39 | 与 `TILE` 同一套枚举 |
| 第7维 | `VALUE` | 0 | 18 | 19 | 通用小数值桶 |
| 第8维 | `FLAG` | 0 | 31 | 32 | 全局标志枚举；含预留空间 |
| 第9维 | `STEP` | 0 | 17 | 18 | 巡目时间桶 |

## 5. TYPE 语义类型

| ID | Key | 类别 | 含义 |
|---:|---|---|---|
| 0 | `PAD` | 特殊 | padding token |
| 1 | `SEP` | 特殊 | 状态快照和事件历史的分隔符 |
| 2 | `STATE_GAME_MODE` | 状态 | 游戏模式 |
| 3 | `STATE_BAKAZE` | 状态 | 当前场风 |
| 4 | `STATE_JIKAZE` | 状态 | 当前视角玩家自风 |
| 5 | `STATE_OYA` | 状态 | 当前庄家 |
| 6 | `STATE_KYOKU_INDEX` | 状态 | 当前是整场游戏中的第几小局 |
| 7 | `STATE_HONBA` | 状态 | 本场数 |
| 8 | `STATE_KYOTAKU` | 状态 | 当前供托数 |
| 9 | `STATE_SCORE` | 状态 | 某玩家当前点数 bucket |
| 10 | `STATE_LEFT_TILES` | 状态 | 当前牌山剩余张数 bucket |
| 11 | `STATE_DORA` | 状态 | 当前公开宝牌指示牌 |
| 12 | `STATE_HAND` | 状态 | 当前视角玩家闭合手牌中的某牌计数 |
| 13 | `STATE_DRAW` | 状态 | 当前视角玩家刚摸到且尚未打出的牌 |
| 14 | `STATE_REACH` | 状态 | 某玩家立直状态 |
| 15 | `STATE_ZHENTING` | 状态 | 当前视角玩家振听状态 |
| 16 | `STATE_OPEN_MELD` | 状态 | 某玩家已经公开的副露摘要 |
| 17 | `EVENT_START_KYOKU` | 兼容 | 小局开始；默认不生成到模型输入事件序列 |
| 18 | `EVENT_DRAW` | 事件 | 摸牌，MJAI `tsumo` |
| 19 | `EVENT_DISCARD` | 事件 | 打牌，MJAI `dahai` |
| 20 | `EVENT_CHI` | 事件 | 吃 |
| 21 | `EVENT_PON` | 事件 | 碰 |
| 22 | `EVENT_DAIMINKAN` | 事件 | 大明杠 |
| 23 | `EVENT_ANKAN` | 事件 | 暗杠 |
| 24 | `EVENT_KAKAN` | 事件 | 加杠 |
| 25 | `EVENT_REACH` | 事件 | 立直宣言 |
| 26 | `EVENT_DORA` | 事件 | 新宝牌指示牌出现 |
| 27 | `EVENT_NUKIDORA` | 事件 | 三麻拔北 |
| 28 | `EVENT_WIN` | 事件 | 和牌，荣和或自摸 |
| 29 | `EVENT_RYUKYOKU` | 事件 | 荒牌流局 |
| 30 | `EVENT_ABORTIVE_RYUKYOKU` | 事件 | 途中流局 |
| 31 | `RESERVED_TYPE_0` | 预留 | 后续可能追加的状态或事件特征 |
| 32 | `RESERVED_TYPE_1` | 预留 | 后续可能追加的状态或事件特征 |
| 33 | `RESERVED_TYPE_2` | 预留 | 后续可能追加的状态或事件特征 |
| 34 | `RESERVED_TYPE_3` | 预留 | 后续可能追加的状态或事件特征 |
| 35 | `RESERVED_TYPE_4` | 预留 | 后续可能追加的状态或事件特征 |

`STATE_HONBA` 表示当前小局的本场数。日麻中，连庄或流局通常会增加本场数；本场数会影响和牌结算，例如常见规则下每 1 本场荣和额外增加 300 点，自摸时每家额外支付 100 点。本协议只把它作为当前状态的数值 bucket 输入模型，不在事件序列中单独记录本场变化。

## 6. ACTOR 和 TARGET

`ACTOR` 和 `TARGET` 使用同一套相对座位枚举。

| ID | Key | 中文名 | 含义 |
|---:|---|---|---|
| 0 | `NONE` | 无 | 不绑定玩家 |
| 1 | `SELF` | 自己 | 当前模型视角玩家 |
| 2 | `SHIMOCHA` | 下家 | 自己的下家 |
| 3 | `TOIMEN` | 对家 | 自己的对家；三麻普通对局中通常不用 |
| 4 | `KAMICHA` | 上家 | 自己的上家 |

四麻相对座位计算：

```text
relative = (absolute_seat - self_seat) mod 4
```

三麻普通对局中 `TOIMEN` 保留不用。

## 7. TILE / TILE2 / TILE3

三个牌槽使用同一套 MJAI 风格枚举。

| ID | Key | 中文名 |
|---:|---|---|
| 0 | `NONE` | 无牌 |
| 1 | `1m` | 一万 |
| 2 | `2m` | 二万 |
| 3 | `3m` | 三万 |
| 4 | `4m` | 四万 |
| 5 | `5m` | 普通五万 |
| 6 | `6m` | 六万 |
| 7 | `7m` | 七万 |
| 8 | `8m` | 八万 |
| 9 | `9m` | 九万 |
| 10 | `1p` | 一筒 |
| 11 | `2p` | 二筒 |
| 12 | `3p` | 三筒 |
| 13 | `4p` | 四筒 |
| 14 | `5p` | 普通五筒 |
| 15 | `6p` | 六筒 |
| 16 | `7p` | 七筒 |
| 17 | `8p` | 八筒 |
| 18 | `9p` | 九筒 |
| 19 | `1s` | 一索 |
| 20 | `2s` | 二索 |
| 21 | `3s` | 三索 |
| 22 | `4s` | 四索 |
| 23 | `5s` | 普通五索 |
| 24 | `6s` | 六索 |
| 25 | `7s` | 七索 |
| 26 | `8s` | 八索 |
| 27 | `9s` | 九索 |
| 28 | `E` | 东 |
| 29 | `S` | 南 |
| 30 | `W` | 西 |
| 31 | `N` | 北 |
| 32 | `P` | 白 |
| 33 | `F` | 发 |
| 34 | `C` | 中 |
| 35 | `5mr` | 赤五万 |
| 36 | `5pr` | 赤五筒 |
| 37 | `5sr` | 赤五索 |
| 38 | `UNKNOWN` | 不可见牌 |

牌槽关联规则：

| TYPE | `TILE` | `TILE2` | `TILE3` |
|---|---|---|---|
| `STATE_HAND` | 手牌牌种 | `NONE` | `NONE` |
| `STATE_DRAW` | 当前摸牌 | `NONE` | `NONE` |
| `STATE_DORA` | 宝牌指示牌 | `NONE` | `NONE` |
| `EVENT_DRAW` | 摸到的牌；不可见为 `UNKNOWN` | `NONE` | `NONE` |
| `EVENT_DISCARD` | 打出的牌 | `NONE` | `NONE` |
| `EVENT_CHI` | 被吃的牌 | consumed 牌1 | consumed 牌2 |
| `EVENT_PON` | 被碰的牌 | consumed 牌1 | consumed 牌2 |
| `EVENT_DAIMINKAN` | 被杠的牌 | consumed 代表牌1 | consumed 代表牌2 |
| `EVENT_ANKAN` | 暗杠牌 | consumed 代表牌1 | consumed 代表牌2 |
| `EVENT_KAKAN` | 加杠牌 | 原碰代表牌1 | 原碰代表牌2 |
| `EVENT_WIN` | 和牌牌 | `NONE` | `NONE` |

## 8. VALUE 通用小数值

`VALUE` 是一个很小的非负整数桶，不表达事件性质、状态种类或动作语义。没有数值含义的 token 统一填 `VALUE_NONE`。

通用编码函数：

```text
encode_value_none() = VALUE_NONE
encode_value(n) = VALUE_n, 0 <= n <= 16
encode_value(n) = VALUE_17_PLUS, n >= 17
```

注意：`VALUE_NONE` 表示该 token 没有数值字段；`VALUE_0` 表示数值 0，`VALUE_1` 表示数值 1，以此类推。

| ID | Key | 含义 |
|---:|---|---|
| 0 | `VALUE_NONE` | 无数值 |
| 1 | `VALUE_0` | 数值 0 |
| 2 | `VALUE_1` | 数值 1 |
| 3 | `VALUE_2` | 数值 2 |
| 4 | `VALUE_3` | 数值 3 |
| 5 | `VALUE_4` | 数值 4 |
| 6 | `VALUE_5` | 数值 5 |
| 7 | `VALUE_6` | 数值 6 |
| 8 | `VALUE_7` | 数值 7 |
| 9 | `VALUE_8` | 数值 8 |
| 10 | `VALUE_9` | 数值 9 |
| 11 | `VALUE_10` | 数值 10 |
| 12 | `VALUE_11` | 数值 11 |
| 13 | `VALUE_12` | 数值 12 |
| 14 | `VALUE_13` | 数值 13 |
| 15 | `VALUE_14` | 数值 14 |
| 16 | `VALUE_15` | 数值 15 |
| 17 | `VALUE_16` | 数值 16 |
| 18 | `VALUE_17_PLUS` | 数值 17 或更大 |

`VALUE` 按 `TYPE` 的使用规则：

| TYPE | VALUE 含义 | 推荐缩放 |
|---|---|---|
| `STATE_GAME_MODE` | 不使用 | `VALUE_NONE` |
| `STATE_BAKAZE` / `STATE_JIKAZE` / `STATE_OYA` | 不使用 | `VALUE_NONE` |
| `STATE_HONBA` | 本场数 | `VALUE_min(honba, 17)` |
| `STATE_KYOTAKU` | 供托数 | `VALUE_min(kyotaku, 17)` |
| `STATE_SCORE` | 分数桶 | 每 5000 点一桶，`VALUE_min(floor(score / 5000), 17)` |
| `STATE_LEFT_TILES` | 剩余牌数桶 | 每 4 张一桶，`VALUE_min(floor(left_tiles / 4), 17)` |
| `STATE_DORA` / `EVENT_DORA` | 宝牌指示牌序号 | 第 1 张为 `VALUE_0`，超过 17 截断 |
| `STATE_HAND` | 当前闭合手牌中该牌数量 | `VALUE_1..VALUE_4` |
| `STATE_DRAW` | 不使用 | `VALUE_NONE` |
| `STATE_REACH` / `STATE_ZHENTING` | 不使用 | `VALUE_NONE` |
| `STATE_OPEN_MELD` | 不使用 | `VALUE_NONE` |
| `STATE_KYOKU_INDEX` | 当前小局序号桶 | `VALUE_min(kyoku_index, 17)` |
| `EVENT_START_KYOKU` | 兼容旧数据的小局序号桶 | 默认不生成；若读取旧数据则使用 `VALUE_min(kyoku_index, 17)` |
| 其他 `EVENT_*` | 默认不使用 | `VALUE_NONE` |

## 9. FLAG 全局标志

`FLAG` 只表达少量 qualitative 标志，不承载计数或 bucket。无标志时使用 `FLAG_NONE`。

| ID | Key | 含义 |
|---:|---|---|
| 0 | `FLAG_NONE` | 无标志 |
| 1 | `GAME_4P_EAST` | 四麻东风 |
| 2 | `GAME_4P_SOUTH` | 四麻半庄 |
| 3 | `GAME_3P_EAST` | 三麻东风 |
| 4 | `GAME_3P_SOUTH` | 三麻半庄 |
| 5 | `REACH_NONE` | 未立直 |
| 6 | `REACH_NORMAL` | 普通立直 |
| 7 | `REACH_DOUBLE` | 双立直 |
| 8 | `REACH_PENDING` | 立直宣言后待确认 |
| 9 | `ZHENTING_FALSE` | 未振听 |
| 10 | `ZHENTING_TRUE` | 振听 |
| 11 | `TSUMOGIRI` | 摸切 |
| 12 | `TEDASHI` | 手切 |
| 13 | `REACH_DECLARE` | 普通立直宣言 |
| 14 | `DOUBLE_REACH_DECLARE` | 双立直宣言 |
| 15 | `RON` | 荣和 |
| 16 | `TSUMO` | 自摸 |
| 17 | `CHI_LOW` | 低位吃 |
| 18 | `CHI_MID` | 中间吃 |
| 19 | `CHI_HIGH` | 高位吃 |
| 20 | `CHI_UNKNOWN` | 吃牌形态未知或不需要区分 |
| 21 | `OPEN` | 明牌、副露、公开 |
| 22 | `CLOSED` | 闭合 |
| 23 | `NUKIDORA` | 拔北属性 |
| 24 | `RYUKYOKU_NORMAL` | 普通荒牌流局 |
| 25 | `RYUKYOKU_ABORTIVE` | 途中流局 |
| 26-31 | `RESERVED_FLAG_*` | 后续扩展使用 |

## 10. STEP 时间位置

`STEP` 初版使用巡目桶。

| ID | Key | 含义 |
|---:|---|---|
| 0 | `STEP_0` | 未入巡，开局状态 |
| 1 | `STEP_1` | 第 1 巡 |
| 2 | `STEP_2` | 第 2 巡 |
| 3 | `STEP_3` | 第 3 巡 |
| 4 | `STEP_4` | 第 4 巡 |
| 5 | `STEP_5` | 第 5 巡 |
| 6 | `STEP_6` | 第 6 巡 |
| 7 | `STEP_7` | 第 7 巡 |
| 8 | `STEP_8` | 第 8 巡 |
| 9 | `STEP_9` | 第 9 巡 |
| 10 | `STEP_10` | 第 10 巡 |
| 11 | `STEP_11` | 第 11 巡 |
| 12 | `STEP_12` | 第 12 巡 |
| 13 | `STEP_13` | 第 13 巡 |
| 14 | `STEP_14` | 第 14 巡 |
| 15 | `STEP_15` | 第 15 巡 |
| 16 | `STEP_16` | 第 16 巡 |
| 17 | `STEP_17_PLUS` | 第 17 巡或更晚 |

## 11. 状态 token 规范

| 状态 | 编码规则 |
|---|---|
| 游戏模式 | `(STATE_GAME_MODE, NONE, NONE, NONE, NONE, NONE, VALUE_NONE, GAME_*, STEP_0)` |
| 场风 | `(STATE_BAKAZE, NONE, NONE, E/S/W/N, NONE, NONE, VALUE_NONE, FLAG_NONE, step)` |
| 自风 | `(STATE_JIKAZE, SELF, NONE, E/S/W/N, NONE, NONE, VALUE_NONE, FLAG_NONE, step)` |
| 庄家 | `(STATE_OYA, oya_actor, NONE, NONE, NONE, NONE, VALUE_NONE, FLAG_NONE, step)` |
| 当前小局序号 | `(STATE_KYOKU_INDEX, NONE, NONE, NONE, NONE, NONE, VALUE_*, FLAG_NONE, STEP_0)` |
| 本场 | `(STATE_HONBA, NONE, NONE, NONE, NONE, NONE, VALUE_*, FLAG_NONE, step)` |
| 供托 | `(STATE_KYOTAKU, NONE, NONE, NONE, NONE, NONE, VALUE_*, FLAG_NONE, step)` |
| 剩余牌数 | `(STATE_LEFT_TILES, NONE, NONE, NONE, NONE, NONE, VALUE_*, FLAG_NONE, step)` |
| 手牌计数 | `(STATE_HAND, SELF, NONE, tile, NONE, NONE, VALUE_n, FLAG_NONE, step)` |
| 当前摸牌 | `(STATE_DRAW, SELF, NONE, tile, NONE, NONE, VALUE_NONE, FLAG_NONE, step)` |
| 分数 | `(STATE_SCORE, actor, NONE, NONE, NONE, NONE, VALUE_*, FLAG_NONE, step)` |
| 宝牌指示牌 | `(STATE_DORA, NONE, NONE, dora_marker, NONE, NONE, VALUE_*, FLAG_NONE, step)` |
| 立直状态 | `(STATE_REACH, actor, NONE, NONE, NONE, NONE, VALUE_NONE, REACH_*, step)` |
| 振听状态 | `(STATE_ZHENTING, SELF, NONE, NONE, NONE, NONE, VALUE_NONE, ZHENTING_*, step)` |
| 已公开副露 | `(STATE_OPEN_MELD, actor, target, called_tile, tile2, tile3, VALUE_NONE, OPEN, step)` |

## 12. 事件 token 规范

| MJAI 语义 | V2 编码 |
|---|---|
| `start_kyoku` | 环境侧初始化状态快照；不生成事件 token |
| `tsumo` | `(EVENT_DRAW, actor, NONE, pai_or_UNKNOWN, NONE, NONE, VALUE_NONE, FLAG_NONE, step)` |
| `dahai` | `(EVENT_DISCARD, actor, NONE, pai, NONE, NONE, VALUE_NONE, TSUMOGIRI/TEDASHI, step)` |
| `reach` | `(EVENT_REACH, actor, NONE, NONE, NONE, NONE, VALUE_NONE, REACH_DECLARE/DOUBLE_REACH_DECLARE, step)` |
| `chi` | `(EVENT_CHI, actor, target, pai, consumed_1, consumed_2, VALUE_NONE, CHI_*, step)` |
| `pon` | `(EVENT_PON, actor, target, pai, consumed_1, consumed_2, VALUE_NONE, OPEN, step)` |
| `daiminkan` | `(EVENT_DAIMINKAN, actor, target, pai, rep_1, rep_2, VALUE_NONE, OPEN, step)` |
| `ankan` | `(EVENT_ANKAN, actor, NONE, pai, rep_1, rep_2, VALUE_NONE, CLOSED, step)` |
| `kakan` | `(EVENT_KAKAN, actor, NONE, pai, rep_1, rep_2, VALUE_NONE, OPEN, step)` |
| `dora` | `(EVENT_DORA, NONE, NONE, dora_marker, NONE, NONE, VALUE_*, FLAG_NONE, step)` |
| `nukidora` | `(EVENT_NUKIDORA, actor, NONE, N, NONE, NONE, VALUE_NONE, NUKIDORA, step)` |
| `hora` | 环境侧和牌结算；默认不生成决策输入事件，兼容旧数据时可映射为 `EVENT_WIN` |
| `ryukyoku` | 环境侧荒牌流局结算；默认不生成决策输入事件，兼容旧数据时可映射为 `EVENT_RYUKYOKU` |
| 途中流局 | 环境侧途中流局结算；默认不生成决策输入事件，兼容旧数据时可映射为 `EVENT_ABORTIVE_RYUKYOKU` |

## 13. MJAI 字段来源

本协议只编码 MJAI 服务端已经确认的状态和事件。实现转换器时，字段来源建议按下表处理：

| V2 信息 | 主要来源 | 说明 |
|---|---|---|
| 环境初始化 | `start_game` | 确定 bot 座位、规则和相对视角，不生成本协议 token |
| 小局状态初始化 | `start_kyoku` | 初始化场风、局号、本场、供托、庄家、初始手牌、初始宝牌指示牌等状态；不生成事件 token |
| 环境结算 | `end_kyoku` / `end_game` | 结算小局或整场游戏，不生成模型决策输入事件 |
| `EVENT_DRAW` | `tsumo` | 摸牌事件；当前视角自己的摸牌可见，其他玩家摸牌通常只知道发生了摸牌 |
| `EVENT_DISCARD` | `dahai` | 打牌事件；`tsumogiri` 字段映射为 `TSUMOGIRI` 或 `TEDASHI` |
| `EVENT_CHI` / `EVENT_PON` | `chi` / `pon` | 副露事件；`actor` 是吃碰者，`target` 是被吃碰牌的来源玩家 |
| `EVENT_DAIMINKAN` / `EVENT_ANKAN` / `EVENT_KAKAN` | `kan` 相关事件 | 按 MJAI 的杠类型映射为大明杠、暗杠或加杠 |
| `EVENT_REACH` | `reach` | 立直宣言事件；普通立直和双立直的区分由事件时机或环境状态判定 |
| `EVENT_WIN` | `hora` | 兼容旧数据的和牌事件；默认由环境侧结算，不生成到决策输入事件 |
| `EVENT_RYUKYOKU` / `EVENT_ABORTIVE_RYUKYOKU` | `ryukyoku` 或结束事件 | 兼容旧数据的流局事件；默认由环境侧结算，不生成到决策输入事件 |
| `STATE_BAKAZE` / `STATE_OYA` / `STATE_KYOKU_INDEX` / `STATE_HONBA` / `STATE_KYOTAKU` | `start_kyoku`，后续由内部状态维护 | 小局内通常不变 |
| `STATE_DORA` | `start_kyoku`、宝牌指示牌变化、`observation` | 表示当前已经公开的宝牌指示牌 |
| `STATE_HAND` / `STATE_DRAW` | `start_kyoku`、`tsumo`、`dahai`、副露事件、`observation` | 只表示当前视角可见的自己手牌状态 |
| `STATE_SCORE` | `observation` 或局终结果 | 用分数 bucket 表示，不直接编码原始点数 |
| `STATE_LEFT_TILES` | `observation` 或内部计数 | 用剩余牌山张数 bucket 表示 |
| `STATE_REACH` / `STATE_ZHENTING` | `reach`、`observation` 或规则状态 | 用 `FLAG` 表示定性状态 |
| `STATE_OPEN_MELD` | `chi`、`pon`、`kan` 事件或 `observation` | 表示已经公开的副露摘要 |
| `request_action` / `possible_actions` / `action_ack` | 环境侧控制消息 | 不生成本协议 token |
| `EVENT_START_KYOKU` | 兼容旧数据 | 默认不生成到模型输入事件序列；读取旧数据时可以兼容解析 |

## 14. 环境侧生命周期处理

生命周期消息用于驱动环境状态机，不属于模型需要学习的局内决策事件。环境消费这些消息后，负责构造或停止构造模型输入序列。

| MJAI 消息 | 环境预期行为 | 是否生成 V2 token |
|---|---|---|
| `start_game` | 保存 bot 座位、规则配置和相对视角映射；初始化整场环境状态 | 否 |
| `start_kyoku` | 清空上一小局事件历史；初始化当前小局状态快照，包括场风、自风、庄家、小局序号、本场、供托、初始手牌、宝牌指示牌等 | 只生成状态 token，不生成事件 token |
| `end_kyoku` | 停止当前小局的决策循环；结算本小局结果；更新分数、供托、本场、庄家变更等环境状态，等待下一次 `start_kyoku` | 否 |
| `end_game` | 标记整场游戏结束；停止继续构造决策输入；保存最终结果或训练样本元数据 | 否 |
| `request_action` | 基于当前状态快照和局内事件历史构造 V2 输入序列；同时生成环境侧 action mask 或候选动作列表并调用模型 | 否，消息本身不进入序列 |
| `action_ack` | 更新环境侧请求状态；若回复被接受，等待后续真实局内事件进入历史；若 stale/rejected/defaulted，则只作为环境日志或错误处理 | 否 |

因此，模型在一次决策时看到的是：

```text
[当前小局状态 tokens...]
[SEP]
[当前小局内已经发生的事件 tokens...]
```

模型不会直接看到 `start_game`、`start_kyoku`、`end_kyoku`、`end_game`、`request_action` 或 `action_ack` 这些控制消息。

## 15. TYPE 到九维的使用总表

下表定义每个 `TYPE` 对九个维度的使用方式。`NONE` 表示该维度必须填对应枚举的空值；`*` 表示按事件或状态内容填入。

| TYPE | ACTOR | TARGET | TILE | TILE2 | TILE3 | VALUE | FLAG | STEP |
|---|---|---|---|---|---|---|---|---|
| `PAD` | `NONE` | `NONE` | `NONE` | `NONE` | `NONE` | `VALUE_NONE` | `FLAG_NONE` | `STEP_0` |
| `SEP` | `NONE` | `NONE` | `NONE` | `NONE` | `NONE` | `VALUE_NONE` | `FLAG_NONE` | `STEP_0` |
| `STATE_GAME_MODE` | `NONE` | `NONE` | `NONE` | `NONE` | `NONE` | `VALUE_NONE` | `GAME_*` | `STEP_0` |
| `STATE_BAKAZE` | `NONE` | `NONE` | 场风牌 | `NONE` | `NONE` | `VALUE_NONE` | `FLAG_NONE` | `step` |
| `STATE_JIKAZE` | `SELF` | `NONE` | 自风牌 | `NONE` | `NONE` | `VALUE_NONE` | `FLAG_NONE` | `step` |
| `STATE_OYA` | 庄家 | `NONE` | `NONE` | `NONE` | `NONE` | `VALUE_NONE` | `FLAG_NONE` | `step` |
| `STATE_HONBA` | `NONE` | `NONE` | `NONE` | `NONE` | `NONE` | 本场数 | `FLAG_NONE` | `step` |
| `STATE_KYOTAKU` | `NONE` | `NONE` | `NONE` | `NONE` | `NONE` | 供托数 | `FLAG_NONE` | `step` |
| `STATE_SCORE` | 玩家 | `NONE` | `NONE` | `NONE` | `NONE` | 分数桶 | `FLAG_NONE` | `step` |
| `STATE_LEFT_TILES` | `NONE` | `NONE` | `NONE` | `NONE` | `NONE` | 剩余牌数桶 | `FLAG_NONE` | `step` |
| `STATE_DORA` | `NONE` | `NONE` | 宝牌指示牌 | `NONE` | `NONE` | 指示牌序号 | `FLAG_NONE` | `step` |
| `STATE_HAND` | `SELF` | `NONE` | 手牌牌种 | `NONE` | `NONE` | 手牌计数 | `FLAG_NONE` | `step` |
| `STATE_DRAW` | `SELF` | `NONE` | 当前摸牌 | `NONE` | `NONE` | `VALUE_NONE` | `FLAG_NONE` | `step` |
| `STATE_REACH` | 玩家 | `NONE` | `NONE` | `NONE` | `NONE` | `VALUE_NONE` | `REACH_*` | `step` |
| `STATE_ZHENTING` | `SELF` | `NONE` | `NONE` | `NONE` | `NONE` | `VALUE_NONE` | `ZHENTING_*` | `step` |
| `STATE_OPEN_MELD` | 副露者 | 来源玩家 | 被鸣牌 | 关联牌1 | 关联牌2 | `VALUE_NONE` | `OPEN` / `CLOSED` | `step` |
| `STATE_KYOKU_INDEX` | `NONE` | `NONE` | `NONE` | `NONE` | `NONE` | 当前小局序号 | `FLAG_NONE` | `STEP_0` |
| `EVENT_START_KYOKU` | `NONE` | `NONE` | 场风牌 | `NONE` | `NONE` | 小局序号 | `FLAG_NONE` | `STEP_0`；兼容旧数据，默认不生成 |
| `EVENT_DRAW` | 摸牌者 | `NONE` | 摸到牌或 `UNKNOWN` | `NONE` | `NONE` | `VALUE_NONE` | `FLAG_NONE` | `step` |
| `EVENT_DISCARD` | 打牌者 | `NONE` | 打出牌 | `NONE` | `NONE` | `VALUE_NONE` | `TSUMOGIRI` / `TEDASHI` | `step` |
| `EVENT_CHI` | 吃牌者 | 来源玩家 | 被吃牌 | consumed 牌1 | consumed 牌2 | `VALUE_NONE` | `CHI_*` | `step` |
| `EVENT_PON` | 碰牌者 | 来源玩家 | 被碰牌 | consumed 牌1 | consumed 牌2 | `VALUE_NONE` | `OPEN` | `step` |
| `EVENT_DAIMINKAN` | 杠牌者 | 来源玩家 | 被杠牌 | 代表牌1 | 代表牌2 | `VALUE_NONE` | `OPEN` | `step` |
| `EVENT_ANKAN` | 杠牌者 | `NONE` | 暗杠牌 | 代表牌1 | 代表牌2 | `VALUE_NONE` | `CLOSED` | `step` |
| `EVENT_KAKAN` | 加杠者 | `NONE` | 加杠牌 | 原碰代表牌1 | 原碰代表牌2 | `VALUE_NONE` | `OPEN` | `step` |
| `EVENT_REACH` | 立直者 | `NONE` | `NONE` | `NONE` | `NONE` | `VALUE_NONE` | `REACH_DECLARE` / `DOUBLE_REACH_DECLARE` | `step` |
| `EVENT_DORA` | `NONE` | `NONE` | 新宝牌指示牌 | `NONE` | `NONE` | 指示牌序号 | `FLAG_NONE` | `step` |
| `EVENT_NUKIDORA` | 拔北者 | `NONE` | `N` | `NONE` | `NONE` | `VALUE_NONE` | `NUKIDORA` | `step` |
| `EVENT_WIN` | 和牌者 | 放铳者或 `NONE` | 和牌牌 | `NONE` | `NONE` | `VALUE_NONE` | `RON` / `TSUMO` | `step`；兼容旧数据，默认不生成 |
| `EVENT_RYUKYOKU` | `NONE` | `NONE` | `NONE` | `NONE` | `NONE` | `VALUE_NONE` | `RYUKYOKU_NORMAL` | `step`；兼容旧数据，默认不生成 |
| `EVENT_ABORTIVE_RYUKYOKU` | `NONE` | `NONE` | `NONE` | `NONE` | `NONE` | `VALUE_NONE` | `RYUKYOKU_ABORTIVE` | `step`；兼容旧数据，默认不生成 |
| `RESERVED_TYPE_*` | `NONE` | `NONE` | `NONE` | `NONE` | `NONE` | `VALUE_NONE` | `FLAG_NONE` | `step` |

## 16. 环境侧决策信息

MJAI 的 `request_action`、`possible_actions` 和 `action_ack` 不属于本协议的事件 token。它们由环境层处理：

| MJAI 信息 | V2 处理方式 |
|---|---|
| `request_action` | 标记当前需要模型决策，但不生成协议 token |
| `possible_actions` | 转成环境侧候选动作表或 action mask |
| bot 回复 | 由环境验证是否匹配当前候选动作 |
| `action_ack.accepted` | 不生成协议 token；等待后续真实事件进入历史 |
| `action_ack.stale` | 不生成协议 token；旧回复被丢弃 |
| `action_ack.rejected` | 不生成协议 token；作为训练/运行错误记录 |
| `action_ack.defaulted` | 不生成协议 token；后续服务器代打产生的真实事件进入历史 |

## 17. 位置关联规则

| 规则 | 说明 |
|---|---|
| 状态区在 `SEP` 前 | 状态 token 不要求严格时间顺序，但建议按固定类型顺序生成 |
| 事件区在 `SEP` 后 | 事件 token 必须按真实发生顺序排列 |
| 决策信息不在序列中 | 合法动作、request id、ack 状态由环境侧保存 |
| 内部 `DECISION` 位置 | 可由模型在协议序列末尾追加，不占用协议枚举 |

## 18. MJAI 到 V2 的映射示例

### 18.1 小局初始化状态

```text
(STATE_BAKAZE, NONE, NONE, E, NONE, NONE, VALUE_NONE, FLAG_NONE, STEP_0)
(STATE_KYOKU_INDEX, NONE, NONE, NONE, NONE, NONE, VALUE_1, FLAG_NONE, STEP_0)
(STATE_DORA, NONE, NONE, 2p, NONE, NONE, VALUE_0, FLAG_NONE, STEP_0)
(STATE_HONBA, NONE, NONE, NONE, NONE, NONE, VALUE_0, FLAG_NONE, STEP_0)
(STATE_KYOTAKU, NONE, NONE, NONE, NONE, NONE, VALUE_0, FLAG_NONE, STEP_0)
(STATE_OYA, SELF, NONE, NONE, NONE, NONE, VALUE_NONE, FLAG_NONE, STEP_0)
(STATE_SCORE, SELF, NONE, NONE, NONE, NONE, VALUE_5, FLAG_NONE, STEP_0)
(STATE_HAND, SELF, NONE, 1m, NONE, NONE, VALUE_2, FLAG_NONE, STEP_0)
```

解释：

- `STATE_BAKAZE` 的 `TILE=E` 表示场风为东，`VALUE` 不参与语义。
- `STATE_KYOKU_INDEX` 的 `VALUE_1` 表示当前小局序号 bucket 为 1。
- `STATE_DORA` 的 `TILE=2p` 表示公开宝牌指示牌，`VALUE_0` 表示第 1 张指示牌。
- `STATE_SCORE` 的 `VALUE_5` 表示分数 bucket 为 5，不表示 5 点。
- `STATE_HAND` 的 `TILE=1m`、`VALUE_2` 表示当前视角手牌中有 2 张 `1m`。
- `start_kyoku` 本身不进入事件历史，它只用于环境生成这些初始状态 token。

### 18.2 他家弃牌后碰牌

```text
(EVENT_DISCARD, KAMICHA, NONE, 5p, NONE, NONE, VALUE_NONE, TEDASHI, STEP_6)
(EVENT_PON, SHIMOCHA, KAMICHA, 5p, 5p, 5p, VALUE_NONE, OPEN, STEP_6)
```

解释：

- `EVENT_DISCARD` 的 `ACTOR=KAMICHA` 表示上家打出 `5p`。
- `FLAG=TEDASHI` 表示该 `dahai` 不是摸切；若 MJAI `tsumogiri=true`，则应填 `TSUMOGIRI`。
- `EVENT_PON` 的 `ACTOR=SHIMOCHA` 表示下家碰牌，`TARGET=KAMICHA` 表示被碰的牌来自上家。
- `TILE2/TILE3` 表示碰牌者用于组成副露的两张关联牌。

### 18.3 杠、翻宝牌、岭上摸牌、弃牌

```text
(EVENT_ANKAN, SELF, NONE, 1s, 1s, 1s, VALUE_NONE, CLOSED, STEP_8)
(EVENT_DORA, NONE, NONE, 7p, NONE, NONE, VALUE_1, FLAG_NONE, STEP_8)
(EVENT_DRAW, SELF, NONE, 5m, NONE, NONE, VALUE_NONE, FLAG_NONE, STEP_8)
(EVENT_DISCARD, SELF, NONE, 9s, NONE, NONE, VALUE_NONE, TEDASHI, STEP_8)
```

解释：

- `EVENT_ANKAN` 的 `FLAG=CLOSED` 表示暗杠，`TARGET=NONE` 表示没有被鸣牌来源玩家。
- `EVENT_DORA` 的 `VALUE_1` 表示这是第 2 张公开宝牌指示牌。
- `EVENT_DRAW` 表示岭上摸牌这一摸牌结果，仍然用普通摸牌事件编码。
- `EVENT_DISCARD` 继续使用 `TSUMOGIRI/TEDASHI` 区分摸切和手切。

## 19. 实现建议

1. 先支持四麻标准局内事件：`tsumo`、`dahai`、`chi`、`pon`、`daiminkan`、`ankan`、`kakan`、`reach`。
2. `start_game`、`start_kyoku`、`end_kyoku`、`end_game` 由环境侧处理；其中 `start_kyoku.kyoku` 映射为 `STATE_KYOKU_INDEX`。
3. 决策训练样本应同时保存 V2 输入序列和环境侧合法动作集合，但合法动作集合不编码为 V2 token。
4. 模型输出可以暂时继续使用现有离散动作空间；环境负责把输出映射到当前合法动作并处理 stale/rejected/defaulted。
5. 数据校验器应检查状态区和事件区一致性，尤其是手牌计数、副露、宝牌数量、立直状态和剩余牌数。
