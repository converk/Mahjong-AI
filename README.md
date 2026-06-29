# Mahjong-AI

本仓库用于整理麻将 AI 的输入协议、动作空间和 Transformer 编码器设计文档。当前内容主要围绕“如何把一局麻将的可见状态与事件历史输入模型，并让模型输出离散动作”展开。

参考协议：[MJAI protocol](https://riichi.dev/docs/protocol)

## 文档说明

| 文件 | 作用 |
|---|---|
| [KyokuEventTupleProtocol.md](KyokuEventTupleProtocol.md) | 定义 `KyokuEventTuple V2` 九维输入协议，用于把当前小局状态和已经发生的局内事件编码成 Transformer encoder 的离散 token 序列。 |
| [KyokuTransformerEncoderDesign.md](KyokuTransformerEncoderDesign.md) | 定义 Transformer encoder 如何消费 `KyokuEventTuple V2` 输入，包括 `input_ids` 形状、九个维度的 embedding 矩阵、`DECISION` token、encoder block 和动作预测头。 |
| [KyokuActionSpace.md](KyokuActionSpace.md) | 定义模型输出侧的离散动作空间，包括 `action_id` 分段、动作模板、上下文补全规则和 450 维动作头约定。 |

## 当前设计边界

- 输入协议参考 MJAI 的事件风格，但不会把 `request_action`、`action_ack`、`start_game`、`start_kyoku`、`end_kyoku`、`end_game` 等控制消息直接放入模型事件序列。
- 模型输入由环境侧构造，基本形式是 `[STATE tokens...] [SEP] [EVENT history tokens...]`。
- 动作空间与输入协议解耦：编码器输入迁移到九维协议后，`KyokuActionSpace V1` 的 `action_id` 枚举和 450 维输出头仍可保持稳定。
