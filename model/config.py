"""Configuration for the Kyoku Transformer encoder."""

from dataclasses import dataclass


@dataclass(frozen=True)
class KyokuTransformerConfig:
    """Hyperparameters fixed by KyokuTransformerEncoderDesign.md."""

    d_model: int = 384
    num_layers: int = 12
    num_heads: int = 12
    ffn_hidden_dim: int = 1152
    action_hidden_dim: int = 1536
    num_actions: int = 450
    num_token_features: int = 9
    type_vocab_size: int = 36
    actor_vocab_size: int = 5
    target_vocab_size: int = 5
    tile_vocab_size: int = 39
    value_vocab_size: int = 19
    flag_vocab_size: int = 32
    step_vocab_size: int = 18
    dropout: float = 0.1
    rms_norm_eps: float = 1e-6
    rope_base: float = 10000.0

    @property
    def head_dim(self) -> int:
        return self.d_model // self.num_heads

    def __post_init__(self) -> None:
        if self.d_model % self.num_heads != 0:
            raise ValueError("d_model must be divisible by num_heads")
        if self.head_dim % 2 != 0:
            raise ValueError("head_dim must be even for RoPE")
        if self.num_token_features != 9:
            raise ValueError("Kyoku input tokens must have exactly 9 features")
