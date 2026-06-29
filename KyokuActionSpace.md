# KyokuActionSpace V1

## 1. 文档作用

本文档定义基于 [KyokuTokenProtocol.md](<D:/env/VSCode Projects/MahjongCopilot/MyCopilot/KyokuTokenProtocol.md:1>) 的动作空间设计。

它回答三个问题：

| 问题 | 说明 |
|---|---|
| 模型输出什么 | Transformer 输出的离散 `action_id` 表示什么语义动作 |
| 如何从离散 id 还原动作 | 如何把 `action_id` 解码成一个结构化动作 |
| 如何把动作表达为七维协议 | 如何把一个具体动作转换成一个 `KyokuToken` 七维元组 |

这里的动作空间不以 MJAI 协议为中心，而是以 `KyokuToken V1` 为中心。也就是说，模型输出的每个动作都必须最终能够落成一个七维事件 token。

`KyokuTokenProtocol` 当前已经为 `TYPE` 维度额外预留了 10 个扩展枚举，但 `KyokuActionSpace V1` 目前不会把任何动作解码到这些预留类型上。当前动作空间只会落到已经正式定义的 `EVENT_*` 类型，预留 `TYPE` 仅服务后续协议扩展。

## 2. 设计原则

`KyokuActionSpace V1` 采用三层结构：

```text
离散 action_id
-> ActionTemplate（模板动作）
-> ActionInstance（结合当前局面补全后的具体动作）
-> 一个事件 KyokuToken
```

三个核心原则：

| 原则 | 说明 |
|---|---|
| 动作表稳定 | 每个 `action_id` 永远表示同一个模板动作，不随当前候选按钮顺序变化 |
| 协议同构 | 每个具体动作都必须能转换为一个事件 `KyokuToken` |
| 上下文补全 | 一部分字段不直接编码进 `action_id`，而是在当前决策窗口中补全 |

这里的职责划分是：

```text
模型负责输出一个动作事件
环境负责根据这个事件更新局面
```

也就是说，模型的一次输出不是“一个动作展开成多条协议事件”，而是“声明一个主事件”。该事件对手牌、副露、立直状态、剩余牌数等造成的影响，由环境模块负责执行状态转移。

例如：

```text
action_id = 0
-> PASS
-> PASS on SHIMOCHA discard 3p
-> (EVENT_PASS, SELF, 3p, SHIMOCHA, VALUE_NONE, NONE, TURN_6)
```

## 3. ActionTemplate 与 ActionInstance

### 3.1 模板动作

模板动作只编码“决策语义本身”，不强行编码所有上下文。

```text
ActionTemplate {
  kind
  static_args
}
```

例如：

| 模板动作 | 含义 |
|---|---|
| `DISCARD(3p, TEDASHI)` | 手切 `3p` |
| `REACH_DISCARD(3p, TSUMOGIRI)` | 立直后摸切 `3p` |
| `CHI(consumed=[3p,5pr], shape=MID)` | 用 `3p` 和 `5pr` 吃成中吃 |
| `PON(consumed=[5p,5pr])` | 用 `5p` 和 `5pr` 碰 |
| `PASS` | 放弃当前可选动作 |
| `WIN_RON` | 荣和 |
| `WIN_TSUMO` | 自摸 |

### 3.2 具体动作

具体动作是在当前决策窗口中，把模板动作补全为完整动作：

```text
ActionInstance {
  kind
  actor = SELF
  tile
  target
  consumed
  flag
  value
  turn
}
```

其中：

| 字段 | 来源 |
|---|---|
| `actor` | 固定为 `SELF` |
| `turn` | 当前状态快照 / 当前决策点巡目 |
| `tile` | 模板动作或当前待响应机会补全 |
| `target` | 当前待响应来源玩家补全 |
| `consumed` | 模板动作中定义的精确手牌组合 |
| `flag` | 由模板动作和当前状态决定 |
| `value` | 由动作类型决定 |

## 4. 为什么需要“上下文补全”

如果把所有动作都展开成“完全具体事件”，动作空间会不必要地膨胀。

例如 `PASS`：

| 写法 | 问题 |
|---|---|
| `PASS_ON_SHIMOCHA_3p_PON_WINDOW` | 过于依赖当前窗口上下文，动作表会爆炸 |
| `PASS` + 当前窗口补全 `tile=3p,target=SHIMOCHA` | 更稳定、更容易训练 |

同理：

| 动作 | 建议 |
|---|---|
| `WIN_RON` | `tile`、`target` 由当前可和牌窗口补全 |
| `RYUKYOKU` | `ABORTIVE_TYPE_*` 由当前流局机会补全 |
| `PON` / `DAIMINKAN` | 被鸣的那张牌由当前窗口补全，`consumed` 由模板动作给出 |

## 5. tile 与 consumed 的基准顺序

### 5.1 动作空间用的 37 张可见牌

动作空间使用 `KyokuTokenProtocol` 中 `TILE` 的可见牌集合，按以下固定顺序展开：

```text
1m 2m 3m 4m 5m 6m 7m 8m 9m
1p 2p 3p 4p 5p 6p 7p 8p 9p
1s 2s 3s 4s 5s 6s 7s 8s 9s
E S W N P F C
5mr 5pr 5sr
```

记为：

```text
ACTION_TILE37
```

### 5.2 `consumed` 的规范顺序

当一个动作带有 `consumed` 元数据时，`consumed` 列表必须先做规范化。

推荐规范顺序与项目现有 `MJAI_TILES_SORTED` 一致：

```text
1m 2m 3m 4m 5mr 5m 6m 7m 8m 9m
1p 2p 3p 4p 5pr 5p 6p 7p 8p 9p
1s 2s 3s 4s 5sr 5s 6s 7s 8s 9s
E S W N P F C
```

这个顺序用于：

| 用途 | 说明 |
|---|---|
| 吃碰杠模板去重 | 不同写法的相同 consumed 组合归一化 |
| 环境状态转移 | 环境在消费 `ActionInstance.consumed` 时拥有稳定顺序 |

## 6. 顶层动作类别

对于普通四麻和普通三麻，`KyokuActionSpace V1` 顶层动作类别定义如下：

| 类别 | 说明 |
|---|---|
| `PASS` | 主动跳过/不操作 |
| `DISCARD` | 普通打牌 |
| `REACH_DISCARD` | 立直并打牌 |
| `CHI` | 吃 |
| `PON` | 碰 |
| `DAIMINKAN` | 大明杠 |
| `ANKAN` | 暗杠 |
| `KAKAN` | 加杠 |
| `WIN_RON` | 荣和 |
| `WIN_TSUMO` | 自摸 |
| `RYUKYOKU` | 主动宣告流局，例如九种九牌 |
| `NUKIDORA` | 三麻拔北 |

其中：

| 类别 | 四麻 | 三麻 |
|---|---|---|
| `CHI` | 可用 | 不可用 |
| `NUKIDORA` | 不可用 | 可用 |
| 其他 | 可用 | 可用 |

## 7. 已定义动作总数与模型输出维度

在“模板动作 + 上下文补全”的设计下，当前协议中已经严格定义的动作模板总数为：

```text
N = 382
```

同时，模型输出头不必与已定义动作数完全相等。当前推荐配置为：

```text
model_action_dim = 450
```

其中：

| 范围 | 含义 |
|---|---|
| `0..381` | 当前 V1 已定义并可解码的动作模板 |
| `382..449` | 预留输出槽位，当前不参与协议解码 |

明细如下：

| 类别 | 数量 | 说明 |
|---|---:|---|
| `PASS` | 1 | 一个通用跳过模板 |
| `DISCARD` | 74 | 37 张牌 × 摸切/手切 |
| `REACH_DISCARD` | 74 | 37 张牌 × 摸切/手切 |
| `CHI` | 81 | 三种花色下所有 consumed 精确组合 |
| `PON` | 37 | 非五牌 31 种 + 三种五牌的赤牌组合 6 种 |
| `DAIMINKAN` | 37 | 非五牌 31 种 + 三种五牌的赤牌组合 6 种 |
| `ANKAN` | 37 | 非五牌 31 种 + 三种五牌的有赤/无赤两种组合 |
| `KAKAN` | 37 | 非五牌 31 种 + 三种五牌的加杠牌有赤/无赤两种 |
| `WIN_RON` | 1 | 荣和模板 |
| `WIN_TSUMO` | 1 | 自摸模板 |
| `RYUKYOKU` | 1 | 主动流局模板 |
| `NUKIDORA` | 1 | 三麻拔北模板 |
| 合计 | **382** | 动作模板总数 |

## 8. action_id 分段

推荐使用固定分段，便于后续 debug、mask 和统计。

### 8.1 已定义动作区间

当前 V1 已定义动作只覆盖前 `382` 个离散 id：

| ID 范围 | 类别 | 数量 |
|---:|---|---:|
| `0` | `PASS` | 1 |
| `1..74` | `DISCARD` | 74 |
| `75..148` | `REACH_DISCARD` | 74 |
| `149..229` | `CHI` | 81 |
| `230..266` | `PON` | 37 |
| `267..303` | `DAIMINKAN` | 37 |
| `304..340` | `ANKAN` | 37 |
| `341..377` | `KAKAN` | 37 |
| `378` | `WIN_RON` | 1 |
| `379` | `WIN_TSUMO` | 1 |
| `380` | `RYUKYOKU` | 1 |
| `381` | `NUKIDORA` | 1 |

### 8.2 预留区间

为了给后续补充合法动作、特殊规则扩展、或更细粒度模板预留空间，模型输出层再额外保留：

| ID 范围 | 类别 | 数量 | 当前处理方式 |
|---:|---|---:|---|
| `382..449` | `RESERVED_ACTION` | 68 | 当前不解码，不生成 `ActionTemplate` |

当前阶段建议：

1. 训练标签只使用 `0..381`
2. 推理阶段只解析 `0..381`
3. 若模型输出落到 `382..449`，视为“未定义动作槽位命中”，应由上层策略拒绝、回退或重新采样

## 9. 各类动作的展开规则

### 9.1 `PASS`

```text
action_id = 0
```

模板：

```text
PASS
```

上下文补全规则：

| 决策窗口 | `tile` | `target` |
|---|---|---|
| 放弃吃/碰/大明杠/荣和 | 当前被响应牌 | 对应来源玩家 |
| 放弃暗杠/加杠/自摸/拔北/九种九牌 | 能确定就填相关牌，否则 `NONE` | 通常 `SELF` 或 `NONE` |

### 9.2 `DISCARD`

数量：

```text
37 张牌 × {TEDASHI, TSUMOGIRI} = 74
```

展开顺序：

1. 按 `ACTION_TILE37` 顺序遍历牌
2. 每张牌先放 `TEDASHI`
3. 再放 `TSUMOGIRI`

模板：

```text
DISCARD(tile, discard_mode)
```

### 9.3 `REACH_DISCARD`

数量：

```text
37 张牌 × {TEDASHI, TSUMOGIRI} = 74
```

展开顺序与 `DISCARD` 一致。

模板：

```text
REACH_DISCARD(tile, discard_mode)
```

双立直不单独占新模板；在具体动作阶段由当前局面补全 `REACH_STATE_DOUBLE`。

### 9.4 `CHI`

数量：

```text
81
```

模板不直接编码 `target`，因为普通四麻吃牌来源固定是 `KAMICHA`，三麻中 `CHI` 不会合法出现。

模板字段：

```text
CHI(consumed=[t1, t2], shape)
```

展开规则：

1. 仅在万/筒/索三门中展开
2. 仅生成能与某个弃牌组成顺子的 consumed 精确组合
3. 若 consumed 包含 5，则区分普通五和赤五
4. consumed 列表先按规范顺序归一化

结果是每门 27 种，共 81 种。

### 9.5 `PON`

数量：

```text
37
```

模板字段：

```text
PON(consumed=[t1, t2])
```

展开规则：

| 牌种 | 模板数 | 说明 |
|---|---:|---|
| 非五牌 31 种 | 31 | consumed 固定为 `[t, t]` |
| `5m / 5p / 5s` | 每种 2 | `[5x,5x]` 与 `[5x,5xr]` |

### 9.6 `DAIMINKAN`

数量：

```text
37
```

模板字段：

```text
DAIMINKAN(consumed=[t1, t2, t3])
```

展开规则：

| 牌种 | 模板数 | 说明 |
|---|---:|---|
| 非五牌 31 种 | 31 | consumed 固定为 `[t, t, t]` |
| `5m / 5p / 5s` | 每种 2 | `[5x,5x,5x]` 与 `[5x,5x,5xr]` |

### 9.7 `ANKAN`

数量：

```text
37
```

模板字段：

```text
ANKAN(kan_tile)
```

这里不直接把四张 `consumed` 全部编码进模板名，而是用 `kan_tile` 标记暗杠类型：

| 牌种 | 模板数 | 说明 |
|---|---:|---|
| 非五牌 31 种 | 31 | `ANKAN(t)` |
| `5m / 5p / 5s` | 每种 2 | `ANKAN(5x)` 与 `ANKAN(5xr)` |

上下文补全时：

| 模板 | `consumed` |
|---|---|
| `ANKAN(5m)` | `[5m,5m,5m,5m]` |
| `ANKAN(5mr)` | `[5mr,5m,5m,5m]` |

### 9.8 `KAKAN`

数量：

```text
37
```

模板字段：

```text
KAKAN(add_tile)
```

展开规则：

| 牌种 | 模板数 | 说明 |
|---|---:|---|
| 非五牌 31 种 | 31 | `KAKAN(t)` |
| `5m / 5p / 5s` | 每种 2 | `KAKAN(5x)` 与 `KAKAN(5xr)` |

### 9.9 `WIN_RON` / `WIN_TSUMO`

数量：

```text
2
```

模板：

```text
WIN_RON
WIN_TSUMO
```

上下文补全规则：

| 模板 | `tile` | `target` | `value` |
|---|---|---|---|
| `WIN_RON` | 当前和牌牌张 | 当前放铳/抢杠来源 | `WIN_TYPE_RON` |
| `WIN_TSUMO` | `NONE` 或当前自摸牌 | `SELF` | `WIN_TYPE_TSUMO` |

### 9.10 `RYUKYOKU`

数量：

```text
1
```

模板：

```text
RYUKYOKU
```

上下文补全规则：

| 情况 | `TYPE` | `VALUE` |
|---|---|---|
| 九种九牌等主动途中流局 | `EVENT_ABORTIVE_RYUKYOKU` | 当前流局类型对应的 `ABORTIVE_TYPE_*` |
| 其他主动声明流局（若后续扩展） | 由具体规则决定 | 由具体规则决定 |

### 9.11 `NUKIDORA`

数量：

```text
1
```

模板：

```text
NUKIDORA
```

上下文补全规则：

| 字段 | 值 |
|---|---|
| `tile` | `N` |
| `target` | `NONE` |
| `value` | `VALUE_NONE` |

## 10. 从 action_id 到具体动作

推荐的解码流程：

```text
1. 先检查 action_id 是否落在 0..381
2. 若是，则根据 action_id 所在区间确定顶层类别
3. 在该类别内部按固定顺序恢复模板参数
4. 读取当前决策窗口，补全 tile / target / turn / value / flag
5. 生成 ActionInstance
6. 将 ActionInstance 转换成一个事件 KyokuToken
7. 若 action_id 落在 382..449，则当前版本不解码，直接视为 RESERVED_ACTION
```

例如：

```text
action_id = 0
-> PASS
-> 当前窗口：下家打出 3p，可碰可跳过
-> PASS(tile=3p, target=SHIMOCHA, turn=6)
-> (EVENT_PASS, SELF, 3p, SHIMOCHA, VALUE_NONE, NONE, TURN_6)
```

## 11. 从具体动作到单个事件 KyokuToken

当前 V1 的核心约束是：

```text
一次模型输出
= 一个 action_id
= 一个 ActionInstance
= 一个事件 KyokuToken
```

环境模块在收到这个事件后，再根据 `ActionInstance` 中的上下文信息和内部规则更新局面。

### 11.1 动作到事件 token 的映射

| 动作 | 事件 KyokuToken |
|---|---|
| `PASS` | `(EVENT_PASS, SELF, tile_or_NONE, target_or_NONE, VALUE_NONE, NONE, TURN_x)` |
| `DISCARD(3p, TEDASHI)` | `(EVENT_DISCARD, SELF, 3p, NONE, VALUE_NONE, TEDASHI, TURN_x)` |
| `DISCARD(3p, TSUMOGIRI)` | `(EVENT_DISCARD, SELF, 3p, NONE, VALUE_NONE, TSUMOGIRI, TURN_x)` |
| `REACH_DISCARD(3p, TEDASHI)` | `(EVENT_DISCARD, SELF, 3p, NONE, VALUE_NONE, REACH, TURN_x)` |
| `REACH_DISCARD(5pr, TSUMOGIRI)` | `(EVENT_DISCARD, SELF, 5pr, NONE, VALUE_NONE, REACH or DOUBLE_REACH, TURN_x)` |
| `CHI` | `(EVENT_CHI, SELF, called_tile, KAMICHA, chi_shape, NONE, TURN_x)` |
| `PON` | `(EVENT_PON, SELF, called_tile, target, VALUE_NONE, NONE, TURN_x)` |
| `DAIMINKAN` | `(EVENT_DAIMINKAN, SELF, called_tile, target, VALUE_NONE, NONE, TURN_x)` |
| `ANKAN` | `(EVENT_ANKAN, SELF, kan_tile, NONE, VALUE_NONE, NONE, TURN_x)` |
| `KAKAN` | `(EVENT_KAKAN, SELF, add_tile, NONE, VALUE_NONE, NONE, TURN_x)` |
| `WIN_RON` | `(EVENT_WIN, SELF, win_tile, target, WIN_TYPE_RON, NONE, TURN_x)` |
| `WIN_TSUMO` | `(EVENT_WIN, SELF, NONE, SELF, WIN_TYPE_TSUMO, NONE, TURN_x)` |
| `RYUKYOKU` | `(EVENT_ABORTIVE_RYUKYOKU, SELF, NONE, NONE, abortive_type, NONE, TURN_x)` |
| `NUKIDORA` | `(EVENT_NUKIDORA, SELF, N, NONE, VALUE_NONE, NONE, TURN_x)` |

### 11.2 环境模块负责的内容

动作解码成事件 token 之后，以下内容不再由模型输出协议继续展开，而是由环境模块负责：

| 事项 | 责任方 |
|---|---|
| 手牌减少/增加 | 环境 |
| 副露形成 | 环境 |
| `consumed` 牌的扣除 | 环境 |
| 立直状态切换 | 环境 |
| 立直棒与分数变化 | 环境 |
| 翻宝、岭上、抢杠等后续流程推进 | 环境 |
| 下一时刻合法动作窗口计算 | 环境 |

换句话说，`ActionInstance` 里的 `consumed`、`reach_type`、`abortive_type` 等信息是环境执行状态转移时使用的动作元数据，而不是继续展开成多条协议事件。

## 12. 几个完整示例

### 12.1 跳过碰牌

当前下家打出 `3p`，自己可以碰，但选择跳过：

```text
ActionTemplate: PASS
ActionInstance: PASS(tile=3p, target=SHIMOCHA, turn=6)
KyokuToken:
(EVENT_PASS, SELF, 3p, SHIMOCHA, VALUE_NONE, NONE, TURN_6)
```

### 12.2 普通手切

```text
ActionTemplate: DISCARD(3p, TEDASHI)
ActionInstance: DISCARD(tile=3p, flag=TEDASHI, turn=6)
KyokuToken:
(EVENT_DISCARD, SELF, 3p, NONE, VALUE_NONE, TEDASHI, TURN_6)
```

### 12.3 立直并摸切

```text
ActionTemplate: REACH_DISCARD(6p, TSUMOGIRI)
ActionInstance: REACH_DISCARD(tile=6p, reach_type=NORMAL, flag=REACH, turn=8)
KyokuToken:
(EVENT_DISCARD, SELF, 6p, NONE, VALUE_NONE, REACH, TURN_8)
```

### 12.4 碰赤五组合

当前上家打出 `5p`，自己用 `5p + 5pr` 碰：

```text
ActionTemplate: PON(consumed=[5p,5pr])
ActionInstance: PON(tile=5p, target=KAMICHA, consumed=[5pr,5p], turn=9)
KyokuToken:
(EVENT_PON, SELF, 5p, KAMICHA, VALUE_NONE, NONE, TURN_9)
```

环境解释：

```text
环境读取 consumed=[5pr,5p]
-> 从当前手牌中扣除 5pr 和 5p
-> 与来自 KAMICHA 的 5p 形成碰
-> 更新副露、手牌、后续可行动窗口
```

### 12.5 九种九牌

```text
ActionTemplate: RYUKYOKU
ActionInstance: RYUKYOKU(type=ABORTIVE_TYPE_1, turn=1)
KyokuToken:
(EVENT_ABORTIVE_RYUKYOKU, SELF, NONE, NONE, ABORTIVE_TYPE_1, NONE, TURN_1)
```

## 13. 与模型输出的关系

模型输出层可以定义为：

```text
logits: float[B, 450]
```

其中：

| 维度范围 | 含义 |
|---|---|
| `logits[:, 0:382]` | 当前协议已定义动作 |
| `logits[:, 382:450]` | 预留动作槽位 |

推理时：

```text
logits
-> argmax / sampling
-> action_id
-> 若 action_id in [0, 381]，则解码为 ActionTemplate
-> ActionInstance（结合当前局面补全）
-> 单个事件 KyokuToken
-> 环境根据该事件执行状态转移
-> 若 action_id in [382, 449]，则命中 RESERVED_ACTION，当前版本不做协议内解码
```

训练时：

```text
训练标签动作
-> ActionInstance
-> 匹配唯一 ActionTemplate
-> action_id
-> 作为分类目标
```

当前训练集若只覆盖基础合法动作，则标签应只落在 `0..381`。

## 14. 当前结论

`KyokuActionSpace V1` 的推荐做法不是先拍一个 `1500`，而是先定义：

```text
固定的 382 个模板动作
```

然后在模型侧使用：

```text
450 维输出头
```

并采用如下规则：

| 输出范围 | 作用 |
|---|---|
| `0..381` | 当前正式定义、可解码、可映射回 `KyokuTokenProtocol` 的动作 |
| `382..449` | 预留位，当前不解析 |

也就是说，当前版本不是“定义 450 个动作”，而是“定义 382 个动作，并给模型保留到 450 维输出容量”。在解码时，仍然只对前 `382` 个离散 id 进行动作补全，并把每个动作映射成一个事件 `KyokuToken`；这个事件对局面的影响由环境模块负责执行。

这样我们同时满足了三件事：

| 目标 | 是否满足 |
|---|---|
| 动作空间稳定 | 是 |
| 能覆盖普通三麻/四麻基础动作 | 是 |
| 每个动作都能回到 `KyokuTokenProtocol` | 是 |
