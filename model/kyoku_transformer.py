"""PyTorch implementation of the Kyoku Transformer encoder architecture."""

from __future__ import annotations

import math

import torch
from torch import Tensor, nn
import torch.nn.functional as F

from .config import KyokuTransformerConfig


class RMSNorm(nn.Module):
    """Root mean square normalization."""

    def __init__(self, dim: int, eps: float = 1e-6) -> None:
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x: Tensor) -> Tensor:
        variance = x.pow(2).mean(dim=-1, keepdim=True)
        return x * torch.rsqrt(variance + self.eps) * self.weight


class RotaryPositionEmbedding(nn.Module):
    """RoPE frequencies applied to query/key tensors shaped [B, H, L, D]."""

    def __init__(self, head_dim: int, base: float = 10000.0) -> None:
        super().__init__()
        if head_dim % 2 != 0:
            raise ValueError("head_dim must be even for RoPE")
        inv_freq = 1.0 / (
            base ** (torch.arange(0, head_dim, 2, dtype=torch.float32) / head_dim)
        )
        self.register_buffer("inv_freq", inv_freq, persistent=False)

    def forward(self, x: Tensor, position_ids: Tensor | None = None) -> Tensor:
        seq_len = x.size(-2)
        if position_ids is None:
            position_ids = torch.arange(seq_len, device=x.device)
        position_ids = position_ids.to(device=x.device, dtype=self.inv_freq.dtype)
        freqs = torch.einsum("l,d->ld", position_ids, self.inv_freq)
        freqs = torch.repeat_interleave(freqs, repeats=2, dim=-1)
        cos = freqs.cos().to(dtype=x.dtype)[None, None, :, :]
        sin = freqs.sin().to(dtype=x.dtype)[None, None, :, :]
        return (x * cos) + (self._rotate_half(x) * sin)

    @staticmethod
    def _rotate_half(x: Tensor) -> Tensor:
        x_even = x[..., 0::2]
        x_odd = x[..., 1::2]
        return torch.stack((-x_odd, x_even), dim=-1).flatten(-2)


class SwiGLUFeedForward(nn.Module):
    """SwiGLU FFN: 384 -> 1152 -> 384 by default."""

    def __init__(self, config: KyokuTransformerConfig) -> None:
        super().__init__()
        self.gate_proj = nn.Linear(config.d_model, config.ffn_hidden_dim)
        self.up_proj = nn.Linear(config.d_model, config.ffn_hidden_dim)
        self.down_proj = nn.Linear(config.ffn_hidden_dim, config.d_model)

    def forward(self, x: Tensor) -> Tensor:
        return self.down_proj(F.silu(self.gate_proj(x)) * self.up_proj(x))


class FullSelfAttentionWithRoPE(nn.Module):
    """Bidirectional multi-head self-attention with RoPE on q/k."""

    def __init__(self, config: KyokuTransformerConfig) -> None:
        super().__init__()
        self.num_heads = config.num_heads
        self.head_dim = config.head_dim
        self.scale = self.head_dim**-0.5
        self.q_proj = nn.Linear(config.d_model, config.d_model)
        self.k_proj = nn.Linear(config.d_model, config.d_model)
        self.v_proj = nn.Linear(config.d_model, config.d_model)
        self.out_proj = nn.Linear(config.d_model, config.d_model)
        self.rope = RotaryPositionEmbedding(config.head_dim, config.rope_base)
        self.attn_dropout = nn.Dropout(config.dropout)
        self.out_dropout = nn.Dropout(config.dropout)

    def forward(self, x: Tensor, attention_mask: Tensor) -> Tensor:
        batch_size, seq_len, _ = x.shape
        q = self._split_heads(self.q_proj(x), batch_size, seq_len)
        k = self._split_heads(self.k_proj(x), batch_size, seq_len)
        v = self._split_heads(self.v_proj(x), batch_size, seq_len)

        q = self.rope(q)
        k = self.rope(k)

        scores = torch.matmul(q, k.transpose(-2, -1)) * self.scale
        if attention_mask is not None:
            key_mask = ~attention_mask.to(dtype=torch.bool)[:, None, None, :]
            scores = scores.masked_fill(key_mask, torch.finfo(scores.dtype).min)

        attn = torch.softmax(scores, dim=-1)
        attn = self.attn_dropout(attn)
        context = torch.matmul(attn, v)
        context = context.transpose(1, 2).contiguous().view(batch_size, seq_len, -1)
        return self.out_dropout(self.out_proj(context))

    def _split_heads(self, x: Tensor, batch_size: int, seq_len: int) -> Tensor:
        x = x.view(batch_size, seq_len, self.num_heads, self.head_dim)
        return x.transpose(1, 2)


class TransformerEncoderBlock(nn.Module):
    """Pre-RMSNorm encoder block with residual attention and SwiGLU FFN."""

    def __init__(self, config: KyokuTransformerConfig) -> None:
        super().__init__()
        self.attn_norm = RMSNorm(config.d_model, config.rms_norm_eps)
        self.attn = FullSelfAttentionWithRoPE(config)
        self.ffn_norm = RMSNorm(config.d_model, config.rms_norm_eps)
        self.ffn = SwiGLUFeedForward(config)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, x: Tensor, attention_mask: Tensor) -> Tensor:
        x = x + self.dropout(self.attn(self.attn_norm(x), attention_mask))
        x = x + self.dropout(self.ffn(self.ffn_norm(x)))
        return x


class KyokuTokenEmbedding(nn.Module):
    """Embeds (TYPE, ACTOR, TARGET, TILE, TILE2, TILE3, VALUE, FLAG, STEP)."""

    def __init__(self, config: KyokuTransformerConfig) -> None:
        super().__init__()
        self.config = config
        self.type_embedding = nn.Embedding(config.type_vocab_size, config.d_model)
        self.actor_embedding = nn.Embedding(config.actor_vocab_size, config.d_model)
        self.target_embedding = nn.Embedding(config.target_vocab_size, config.d_model)
        self.tile_embedding = nn.Embedding(config.tile_vocab_size, config.d_model)
        self.tile2_embedding = nn.Embedding(config.tile_vocab_size, config.d_model)
        self.tile3_embedding = nn.Embedding(config.tile_vocab_size, config.d_model)
        self.value_embedding = nn.Embedding(config.value_vocab_size, config.d_model)
        self.flag_embedding = nn.Embedding(config.flag_vocab_size, config.d_model)
        self.step_embedding = nn.Embedding(config.step_vocab_size, config.d_model)

    def forward(self, input_ids: Tensor) -> Tensor:
        if input_ids.size(-1) != self.config.num_token_features:
            raise ValueError("input_ids must have shape [B, L, 9]")

        return (
            self.type_embedding(input_ids[..., 0])
            + self.actor_embedding(input_ids[..., 1])
            + self.target_embedding(input_ids[..., 2])
            + self.tile_embedding(input_ids[..., 3])
            + self.tile2_embedding(input_ids[..., 4])
            + self.tile3_embedding(input_ids[..., 5])
            + self.value_embedding(input_ids[..., 6])
            + self.flag_embedding(input_ids[..., 7])
            + self.step_embedding(input_ids[..., 8])
        )


class KyokuTransformerEncoder(nn.Module):
    """Kyoku Transformer encoder producing action logits shaped [B, 450]."""

    def __init__(self, config: KyokuTransformerConfig | None = None) -> None:
        super().__init__()
        self.config = config or KyokuTransformerConfig()
        self.token_embedding = KyokuTokenEmbedding(self.config)
        self.decision_token = nn.Parameter(torch.empty(1, 1, self.config.d_model))
        self.layers = nn.ModuleList(
            [TransformerEncoderBlock(self.config) for _ in range(self.config.num_layers)]
        )
        self.action_head = nn.Sequential(
            RMSNorm(self.config.d_model, self.config.rms_norm_eps),
            nn.Linear(self.config.d_model, self.config.action_hidden_dim),
            nn.SiLU(),
            nn.Dropout(self.config.dropout),
            nn.Linear(self.config.action_hidden_dim, self.config.num_actions),
        )
        self.reset_parameters()

    def reset_parameters(self) -> None:
        nn.init.normal_(self.decision_token, mean=0.0, std=0.02)

    def forward(self, input_ids: Tensor, attention_mask: Tensor) -> Tensor:
        if input_ids.dim() != 3:
            raise ValueError("input_ids must have shape [B, L, 9]")
        if attention_mask.dim() != 2:
            raise ValueError("attention_mask must have shape [B, L]")
        if input_ids.shape[:2] != attention_mask.shape:
            raise ValueError("input_ids and attention_mask must share [B, L]")

        x = self.token_embedding(input_ids.long())
        batch_size = x.size(0)
        decision_token = self.decision_token.expand(batch_size, -1, -1)
        x = torch.cat([x, decision_token], dim=1)

        decision_mask = torch.ones(
            batch_size, 1, dtype=torch.bool, device=attention_mask.device
        )
        extended_attention_mask = torch.cat(
            [attention_mask.to(dtype=torch.bool), decision_mask], dim=1
        )

        for layer in self.layers:
            x = layer(x, extended_attention_mask)

        h_decision = x[:, -1, :]
        return self.action_head(h_decision)


def count_parameters(module: nn.Module) -> int:
    """Return the number of trainable parameters in a module."""

    return sum(param.numel() for param in module.parameters() if param.requires_grad)
