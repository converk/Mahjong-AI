# KyokuTransformer 编码器设计

## 1. 文档作用与意义

本文档用于说明 `KyokuEventTuple V2` 九维协议之上的 Transformer 编码器结构。`KyokuEventTuple V2` 定义“如何把一局普通四麻/三麻对局表示成九维 token 序列”，本文档定义“模型如何消费这些 token，并输出动作空间上的预测结果”。

这份文档的作用是固定模型侧输入输出契约、内部层结构和暂定超参数。后续实现、训练脚本、数据集构造和动作空间设计都应以本文档为基础，但本文档不定义完整动作空间，也不处理合法动作 mask。

## 2. 结构决策摘要

我建议当前版本采用中等规模、现代化的 encoder-only Transformer：

| 模块 | 决策 |
|---|---|
| 输入协议 | `KyokuEventTuple V2` 九维整数 token |
| token embedding 维度 | `d_model = 384` |
| 序列聚合方式 | embedding 后追加可学习 `DECISION` token，使用其最终 hidden state |
| attention | full attention，非 causal |
| 位置编码 | RoPE，作用于 self-attention 的 query/key |
| Transformer 层数 | 12 层 |
| attention heads | 12 heads |
| head 维度 | `32` |
| Norm | Pre-Norm + RMSNorm |
| FFN | SwiGLU FFN |
| FFN hidden 维度 | `1152` |
| 残差连接 | 每个 attention 子层和 FFN 子层都使用 residual |
| 动作头 | 两层 MLP，`384 -> 1536 -> 450` |
| 估算参数量 | 约 `24.43M` |
| 输出 | `logits: float[B, 450]` |

这个结构的取舍是：`d_model=384` 比 256 维有更强的 token 表达能力，12 层 full attention 能更充分地建模局面状态与本局事件序列之间的交互，同时参数量仍处在可训练的中等规模。`DECISION` token 比直接取最后一个事件 token 更稳定，SwiGLU + RMSNorm + Pre-Norm 是当前 Transformer 实现中比较稳妥的默认组合。

## 3. 调研依据

这次结构选择参考了以下公开论文：

| 方向 | 依据 | 对本设计的影响 |
|---|---|---|
| Transformer encoder | [Attention Is All You Need](https://arxiv.org/abs/1706.03762) | 使用 self-attention、FFN、residual 的基本 encoder block |
| RoPE | [RoFormer: Enhanced Transformer with Rotary Position Embedding](https://arxiv.org/abs/2104.09864) | 使用 RoPE 表达序列位置信息，并保留相对位置建模能力 |
| SwiGLU | [GLU Variants Improve Transformer](https://arxiv.org/abs/2002.05202) | 用 SwiGLU 替代传统 ReLU/GELU FFN，提高 FFN 表达能力 |
| RMSNorm | [Root Mean Square Layer Normalization](https://arxiv.org/abs/1910.07467) | 用 RMSNorm 替代 LayerNorm，结构更简单、计算更轻 |

这些论文并不是麻将任务的直接最优证明，但它们给出了现代 Transformer block 的可靠默认组件。麻将局面序列长度中等、输入结构强、动作预测是分类任务；当前选择 `384 x 12` 作为默认规格，是在表达能力、训练成本和后续扩展空间之间的折中。

## 4. 输入参数结构

### 4.1 原始输入

模型原始输入是九维整数 token 序列：

```text
input_ids: int64[B, L, 9]
```

其中：

| 维度 | 含义 |
|---|---|
| `B` | batch size |
| `L` | 九维 token 序列长度，包含状态快照、`SEP`、事件序列和可能的 padding |
| `9` | 九维 token，顺序固定为 `(TYPE, ACTOR, TARGET, TILE, TILE2, TILE3, VALUE, FLAG, STEP)` |

九个维度的当前取值范围来自 `KyokuEventTuple V2`：

| 维度 | 范围 | 词表大小 |
|---|---:|---:|
| `TYPE` | `0..35` | 36 |
| `ACTOR` | `0..4` | 5 |
| `TARGET` | `0..4` | 5 |
| `TILE` | `0..38` | 39 |
| `TILE2` | `0..38` | 39 |
| `TILE3` | `0..38` | 39 |
| `VALUE` | `0..18` | 19 |
| `FLAG` | `0..31` | 32 |
| `STEP` | `0..17` | 18 |

### 4.2 Padding mask

为了支持 batch 内不同长度的序列，需要传入 padding mask：

```text
attention_mask: bool[B, L]
```

含义如下：

| 值 | 含义 |
|---|---|
| `true` / `1` | 真实九维 token，参与 attention |
| `false` / `0` | padding token，不参与 attention |

模型内部追加 `DECISION` token 后，attention mask 也要同步扩展一位：

```text
extended_attention_mask = concat(attention_mask, ones[B, 1])
```

## 5. Embedding 层

每个九维 token 的九个维度分别使用独立 embedding 矩阵。隐藏维度固定为：

```text
d_model = 384
```

各 embedding 表尺寸为：

| Embedding | 尺寸 |
|---|---:|
| `type_embedding` | `36 x 384` |
| `actor_embedding` | `5 x 384` |
| `target_embedding` | `5 x 384` |
| `tile_embedding` | `39 x 384` |
| `tile2_embedding` | `39 x 384` |
| `tile3_embedding` | `39 x 384` |
| `value_embedding` | `19 x 384` |
| `flag_embedding` | `32 x 384` |
| `step_embedding` | `18 x 384` |

单个九维 token 的初始向量由九个维度的 embedding 相加得到：

```text
x_i =
    Emb_TYPE[type_i]
  + Emb_ACTOR[actor_i]
  + Emb_TARGET[target_i]
  + Emb_TILE[tile_i]
  + Emb_TILE2[tile2_i]
  + Emb_TILE3[tile3_i]
  + Emb_VALUE[value_i]
  + Emb_FLAG[flag_i]
  + Emb_STEP[step_i]
```

因此九维 token embedding 的形状为：

```text
x_tokens: float[B, L, 384]
```

## 6. DECISION token

当前版本追加一个可学习的 `DECISION` token，用于聚合整段输入序列的信息，并作为动作预测头的输入。

`DECISION` token 是模型内部参数，不属于 `KyokuEventTuple V2` 九维协议，也不需要占用 `TYPE` 枚举 ID。这样可以保持数据协议稳定：

```text
decision_embedding: float[1, 1, 384]
```

每个 batch 中复制一份并追加到序列尾部：

```text
x = concat(x_tokens, decision_embedding.expand(B, 1, 384), dim=1)
```

追加后：

```text
x: float[B, L + 1, 384]
extended_attention_mask: bool[B, L + 1]
```

最终动作预测使用 `DECISION` 位置的输出，而不是原始序列最后一个九维 token：

```text
h_decision = hidden_states[:, -1, :]
```

这样比“直接取最后一个事件 token”更稳，因为最后一个事件 token 的语义可能是打牌、摸牌、碰牌、宝牌翻开等不同事件，而 `DECISION` token 的职责始终是聚合并服务于下游动作预测。

## 7. 位置编码与 full attention

编码器使用 full attention，也就是非因果、双向注意力：

```text
每个真实 token 可以 attend 到序列中的所有真实 token
DECISION token 也可以 attend 到所有真实 token
```

这里不使用 causal mask，因为目标不是预测下一个 token，而是根据“当前状态快照 + 本局事件序列”预测当前决策点动作 logits。

位置编码使用 RoPE，即 Rotary Position Embedding。RoPE 不直接加到 token embedding 上，而是在每一层 self-attention 中作用于 query 和 key：

```text
q_rot = RoPE(q, position)
k_rot = RoPE(k, position)
attention(q_rot, k_rot, v)
```

位置编号按扩展后的输入序列顺序从 0 开始：

```text
position_ids = [0, 1, 2, ..., L]
```

其中最后一个位置 `L` 对应 `DECISION` token。

## 8. Transformer encoder block

编码器主体由 12 个相同结构的 Transformer encoder block 堆叠而成。

### 8.1 超参数

| 参数 | 值 | 说明 |
|---|---:|---|
| `d_model` | 384 | token 隐藏维度 |
| `num_layers` | 12 | 编码器层数 |
| `num_heads` | 12 | multi-head attention 头数 |
| `head_dim` | 32 | `384 / 12 = 32` |
| `ffn_hidden_dim` | 1152 | SwiGLU 中间维度，约为 `3 * d_model` |
| `dropout` | 0.1 | 初始训练建议值 |
| `attention_type` | full attention | 非 causal attention |
| `position_encoding` | RoPE | 作用于每层 attention 的 query/key |
| `norm` | RMSNorm | Pre-Norm 结构 |

### 8.2 Block 结构

每一层采用 Pre-Norm 结构，attention 和 FFN 两个子层都使用残差连接：

```text
x = x + SelfAttention(RMSNorm(x), mask, rope)
x = x + SwiGLU_FFN(RMSNorm(x))
```

展开后：

```text
输入 x: [B, L + 1, 384]

1. x_norm = RMSNorm(x)
2. attn_out = FullSelfAttentionWithRoPE(x_norm, extended_attention_mask)
3. x = x + Dropout(attn_out)

4. x_norm = RMSNorm(x)
5. ffn_out = SwiGLU_FFN(x_norm)
6. x = x + Dropout(ffn_out)
```

这种结构的优点是训练稳定、实现直接，也方便后续加深层数。

### 8.3 Attention 子层

多头注意力参数：

```text
q_proj: Linear(384, 384)
k_proj: Linear(384, 384)
v_proj: Linear(384, 384)
o_proj: Linear(384, 384)
```

reshape 后：

```text
q, k, v: [B, 12, L + 1, 32]
```

RoPE 作用于 `q` 和 `k`，不作用于 `v`。

### 8.4 SwiGLU FFN 子层

FFN 使用 SwiGLU，而不是普通 `Linear -> GELU -> Linear`：

```text
gate = SiLU(W_gate x)
up = W_up x
hidden = gate * up
out = W_down hidden
```

对应线性层尺寸为：

```text
W_gate: Linear(384, 1152)
W_up:   Linear(384, 1152)
W_down: Linear(1152, 384)
```

SwiGLU 相比普通 GELU FFN 多了门控分支，表达能力更强；`ffn_hidden_dim=1152` 是在 `d_model=384` 下兼顾参数量和表达力的折中。

## 9. 动作预测头

动作空间当前已经定义前 `382` 个动作，并保留到 `450` 维输出，因此输出维度定义为：

```text
num_actions = 450
```

动作预测头使用两层 MLP，而不是单层线性层：

```text
action_head:
  RMSNorm(384)
  Linear(384, 1536)
  SiLU
  Dropout(0.1)
  Linear(1536, 450)
```

输入为 `DECISION` token 的最终隐藏状态：

```text
h_decision: float[B, 384]
```

输出为动作 logits：

```text
logits: float[B, 450]
```

使用两层动作头的原因是：Transformer encoder 已经负责序列交互，但动作空间本身可能有复杂的非线性边界，例如切牌、吃碰杠、立直、和牌等动作并不只是线性可分。`384 -> 1536 -> 450` 给分类头增加一层轻量非线性，同时不会明显增加主干复杂度。

## 10. Forward 接口草案

模型 forward 的概念接口如下：

```python
def forward(
    input_ids: LongTensor,      # [B, L, 9]
    attention_mask: BoolTensor, # [B, L]
) -> FloatTensor:              # [B, 450]
    ...
```

内部主要步骤：

```text
1. 拆分 input_ids 的九个维度
2. 分别查九张 embedding 表
3. 九个 embedding 相加得到 x_tokens: [B, L, 384]
4. 在序列尾部追加 learnable DECISION token: [B, L + 1, 384]
5. 扩展 attention_mask: [B, L + 1]
6. 输入 12 层 RoPE full-attention Transformer encoder
7. 取 DECISION token 的最终 hidden state: [B, 384]
8. 经过两层动作预测 MLP 输出 logits: [B, 450]
```

## 11. 训练输出

训练时通常直接把 `logits` 交给交叉熵损失：

```text
loss = CrossEntropyLoss(logits, target_action_id)
```

当前阶段不考虑合法动作 mask。模型先学习从局面序列到目标动作 ID 的分类能力，合法动作过滤、mask 格式和动作空间枚举会在后续阶段单独设计。

## 12. 当前待定项

| 待定项 | 当前处理 |
|---|---|
| 动作空间枚举 | 当前输出 450 维，其中前 382 维已定义，后 68 维保留 |
| 最大序列长度 `L` | 需要根据牌谱统计和显存预算确定 |
| dropout | 先使用 `0.1`，后续可实验 `0.0`、`0.05`、`0.1` |
| 层数扩展 | 默认 12 层；如果训练欠拟合且资源允许，再考虑 16 层 |
| 动作头维度 | 默认 `1536`；动作空间确定后可重新评估 |

## 13. 设计摘要

| 项 | 当前设计 |
|---|---|
| 输入 | `input_ids: int64[B, L, 9]` |
| 九维 token | `(TYPE, ACTOR, TARGET, TILE, TILE2, TILE3, VALUE, FLAG, STEP)` |
| token embedding | 九个维度独立 embedding 后相加 |
| 隐藏维度 | `384` |
| 聚合 token | 模型内部追加 learnable `DECISION` token |
| attention | full attention |
| 位置编码 | RoPE |
| Transformer 层数 | 12 |
| attention heads | 12 |
| Norm | Pre-Norm + RMSNorm |
| FFN | SwiGLU，`384 -> 1152 -> 384` |
| 动作头 | `RMSNorm -> Linear(384, 1536) -> SiLU -> Linear(1536, 450)` |
| 动作头输入 | `float[B, 384]` |
| 动作头输出 | `float[B, 450]` |
| 输出含义 | 450 个动作槽位的 logits，其中前 382 个当前已定义 |
| 估算参数量 | 约 `24.43M` |
