import json
from dataclasses import dataclass
from typing import List, Optional, Tuple

import torch
import torch.distributed.checkpoint as dcp
from torch import nn
from torch.distributed.checkpoint.state_dict import StateDictOptions, get_model_state_dict, set_model_state_dict
from transformers import T5EncoderModel, T5Tokenizer

from hypercartoon.models.cogvideo.prompts import SceneDescription, blend_embeddings, load_prompts, split_video  # noqa: F401
from hypercartoon.infra.checkpoint import MODEL_STATE_DICT_KEY
from hypercartoon.infra.config_manager import JobConfig
from hypercartoon.infra.parallelisms import TORCH_DTYPE_MAP, apply_parallelisms
from hypercartoon.infra.state_load import load_model_state
from hypercartoon.infra.step_cache import StepCache
from hypercartoon.models.cogvideo.model import CogVideoX
from hypercartoon.models.cogvideo.utils import DiscreteDenoiser, VPSDEDPMPP2MSampler, cast_rotary_freqs
from hypercartoon.models.configs import ModelConfig, VaeModelConfig
from hypercartoon.models.vae.autoencoder import VideoAutoencoderInferenceWrapper


class PromptManager:
    """Handle loading and processing of text prompts for video generation."""

    @staticmethod
    def get_prompts(input_file: str) -> List[Tuple[List[str], Optional[List[str]]]]:
        out = []
        for scenes in load_prompts(input_file):
            texts, negs, _, _ = split_video(scenes)
            out.append((texts, negs))
        return out

    @staticmethod
    def get_prompts_with_mix(input_file: str):
        """-> [(texts, neg_texts, alt_texts | None, mix)]: alt_texts/mix blend two styles in embedding space."""
        return [split_video(scenes) + (next((s.control for s in scenes if s.control), None),) for scenes in load_prompts(input_file)]


class ModelLoader:
    """Handle loading and initialization of models for inference."""

    @staticmethod
    def load_t5_encoder(job_config: JobConfig, device: str) -> Tuple[T5Tokenizer, T5EncoderModel]:
        """
        Load and initialize the T5 tokenizer and encoder model.

        Returns:
            Tuple of (tokenizer, encoder)
        """
        t5_dir = job_config.eval.t5_model_dir
        assert t5_dir is not None, "T5 model directory not provided"

        tokenizer = T5Tokenizer.from_pretrained(t5_dir)
        encoder = T5EncoderModel.from_pretrained(t5_dir, torch_dtype=TORCH_DTYPE_MAP[job_config.eval.dtype])

        print(f"Adding scene tokens to tokenizer... {encoder.config.vocab_size}", end=" -> ")
        tokenizer.add_special_tokens({"additional_special_tokens": [SCENE_END_TOKEN, SCENE_START_TOKEN]})
        encoder.resize_token_embeddings(len(tokenizer))
        print(f"{encoder.config.vocab_size}")

        encoder = encoder.to(device)  # type: ignore
        encoder.eval()

        return tokenizer, encoder

    @staticmethod
    def load_cogvideox_model(
        job_config: JobConfig, effective_rank: int, effective_world_size: int, device: str
    ) -> CogVideoX:
        """
        Load and initialize the CogVideoX model.

        Returns:
            Initialized CogVideoX model
        """
        model_config = ModelConfig.get_preset(job_config.model.size, job_config.model.video_length, job_config)

        with torch.device("meta"):
            model = CogVideoX(model_config, effective_rank=effective_rank, effective_world_size=effective_world_size)

        # cogvideo trains with freqs buffers cast to model dtype
        cast_rotary_freqs(model, TORCH_DTYPE_MAP[job_config.parallelism.fsdp_unsharded_dtype])

        apply_parallelisms(model, job_config)

        model.to_empty(device=device)
        model.init_ssm_weights()

        # Finetuned checkpoints are wrapped ({MODEL_STATE_DICT_KEY: ...}), converted ones are bare; checkpoints that predate the
        # optional control adapters are loaded without them (adapters keep their zero initialisation).
        state_dict = load_model_state(
            lambda: get_model_state_dict(model),
            lambda sd, path: dcp.load(state_dict=sd, checkpoint_id=path),  # type: ignore
            job_config.checkpoint.init_state_dir,
            MODEL_STATE_DICT_KEY,
        )

        set_model_state_dict(model, model_state_dict=state_dict, options=StateDictOptions(strict=True))

        model.eval()
        return model

    @staticmethod
    def load_vae_model(job_config: JobConfig, device: str) -> VideoAutoencoderInferenceWrapper:
        """
        Load and initialize the VAE model.

        Returns:
            Initialized VAE model
        """
        vae_checkpoint_path = job_config.eval.vae_checkpoint_path
        vae_model = VideoAutoencoderInferenceWrapper(
            vae_checkpoint_path,
            VaeModelConfig.get_encoder_config(),
            VaeModelConfig.get_decoder_config(),
            scale_factor=job_config.eval.vae_scale_factor,
        ).to(device)

        vae_model.to(TORCH_DTYPE_MAP[job_config.eval.dtype])
        vae_model.eval()
        return vae_model


class TextEncoder:
    """Handle encoding of text prompts for the model."""

    @staticmethod
    @torch.no_grad()
    def encode_text(
        tokenizer: T5Tokenizer, encoder: T5EncoderModel, prompts: List[str], device: str, maxlen: int, dtype
    ) -> torch.Tensor:
        """
        Encode text prompts using the T5 encoder.

        Returns:
            Tensor of encoded text embeddings
        """
        inputs = tokenizer(
            prompts,
            truncation=True,
            return_length=True,
            max_length=maxlen,
            padding="max_length",
            return_tensors="pt",
        ).to(device)

        with torch.autocast("cuda", enabled=False):
            outputs = encoder(input_ids=inputs["input_ids"])

        embeddings = outputs.last_hidden_state

        # Handle multi-scene vs single prompt differently
        if len(prompts) > 1:
            embeddings = embeddings.unsqueeze(0)

        return embeddings.to(dtype=dtype)


class DenoiserSampler:
    def __init__(
        self,
        model: nn.Module,
        config: JobConfig,
        dtype,
        effective_rank: int,
        seed: int = 0,
        device: str = "cuda",
        use_wandb: bool = False,
    ):
        self.sampler = VPSDEDPMPP2MSampler(
            denoiser=DiscreteDenoiser(
                model,
                num_idx=config.denoiser.num_idx,
                quantize_c_noise=config.denoiser.quantize_c_noise,
                dtype=dtype,
            ),
            discretization_config={"shift_scale": config.discretization.shift_scale},
            guider_config={
                "scale": config.guider.scale,
                "exp": config.guider.exp,
                "num_steps": config.eval.num_denoising_steps,
            },
            verbose=True,
            device=device,
            num_steps=config.eval.num_denoising_steps,
            use_wandb=use_wandb,
        )

        self.model = model
        if config.eval.enhance_weight > 0:
            for layer in model.layers:
                layer.seq_modeling_block.enhance_weight = config.eval.enhance_weight
        self.num_steps = config.eval.num_denoising_steps
        if config.eval.step_cache_threshold > 0:
            model.step_cache = StepCache(config.eval.step_cache_threshold, streams=2)

        self.noise_generator = torch.Generator(device="cuda")
        self.noise_generator.manual_seed(effective_rank + seed)

        self.device = device
        self.dtype = dtype

    @torch.no_grad()
    def sample(self, text_emb: torch.Tensor, neg_emb: torch.Tensor, shape: tuple, batch_size: int, control=None):
        randn = torch.randn(batch_size, *shape, device=self.device, generator=self.noise_generator, dtype=torch.float32)

        cond = {
            "crossattn": text_emb
        }  # compatability with sat.sgm.modules.diffusionmodules.sampling.VPSDEDPMPP2MSampler
        uc = {
            "crossattn": neg_emb,
        }  # compatability with sat.sgm.modules.diffusionmodules.sampling.VPSDEDPMPP2MSampler

        cache = getattr(self.model, "step_cache", None)
        if cache is not None:
            cache.reset(total_calls=self.num_steps * cache.streams)
        if control is not None:  # same control for the unconditional and the conditional pass
            cond["control"] = control
            uc["control"] = control
        samples = self.sampler(randn, cond, uc)
        if cache is not None:
            print(f"[step cache] {cache.stats()}")
        samples = samples.to(self.dtype)
        return samples
