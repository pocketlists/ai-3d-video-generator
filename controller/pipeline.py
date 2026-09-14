"""
Pipeline definition — declares the 20-stage pipeline and dependencies.

Each stage corresponds to one GitHub Actions job. The dependency graph
determines which jobs can run in parallel and which must wait.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class PipelineStage:
    """A single stage in the video generation pipeline."""
    name: str
    job_name: str
    workflow: str
    depends_on: List[str] = field(default_factory=list)
    parallel: bool = False
    description: str = ""

    @property
    def can_run_parallel(self) -> bool:
        return self.parallel


PIPELINE_STAGES: List[PipelineStage] = [
    PipelineStage("receive_request", "receive-request", "01_receive_request",
                 description="Receive generation request from Telegram"),
    PipelineStage("ai_planning", "ai-planning", "02_ai_planning",
                 depends_on=["receive_request"],
                 description="AI plans the video structure and storyboard"),
    PipelineStage("script_breakdown", "script-breakdown", "03_script_breakdown",
                 depends_on=["ai_planning"],
                 description="Break script into scenes and shots"),
    PipelineStage("asset_collection", "asset-collection", "04_asset_collection",
                 depends_on=["script_breakdown"],
                 description="Collect and generate all required assets"),
    PipelineStage("characters", "characters", "05_characters",
                 depends_on=["script_breakdown"], parallel=True,
                 description="Generate character models and textures"),
    PipelineStage("environments", "environments", "06_environments",
                 depends_on=["script_breakdown"], parallel=True,
                 description="Generate environment/scene models"),
    PipelineStage("props", "props", "07_props",
                 depends_on=["script_breakdown"], parallel=True,
                 description="Generate prop models"),
    PipelineStage("animation", "animation", "08_animation",
                 depends_on=["characters", "environments", "props"],
                 description="Generate animation keyframes and motion data"),
    PipelineStage("camera", "camera", "09_camera",
                 depends_on=["environments"],
                 description="Generate camera paths and keyframes"),
    PipelineStage("lighting", "lighting", "10_lighting",
                 depends_on=["environments"],
                 description="Set up lighting rigs and light animation"),
    PipelineStage("voice_tts", "voice-tts", "11_voice_tts",
                 depends_on=["script_breakdown"], parallel=True,
                 description="Generate voice-over via TTS"),
    PipelineStage("music", "music", "12_music",
                 depends_on=["script_breakdown"], parallel=True,
                 description="Generate or select background music"),
    PipelineStage("sfx", "sfx", "13_sfx",
                 depends_on=["script_breakdown"], parallel=True,
                 description="Generate sound effects"),
    PipelineStage("lip_sync", "lip-sync", "14_lip_sync",
                 depends_on=["voice_tts", "characters"],
                 description="Generate lip-sync data from voice audio"),
    PipelineStage("blender_assembly", "blender-assembly", "15_blender_assembly",
                 depends_on=["animation", "camera", "lighting", "lip_sync"],
                 description="Assemble the complete Blender scene"),
    PipelineStage("render_workers", "render-workers", "16_render_workers",
                 depends_on=["blender_assembly"], parallel=True,
                 description="Distributed parallel rendering of frames/clips"),
    PipelineStage("quality_check", "quality-check", "17_quality_check",
                 depends_on=["render_workers"],
                 description="Validate rendered output quality"),
    PipelineStage("ffmpeg_assembly", "ffmpeg-assembly", "18_ffmpeg_assembly",
                 depends_on=["quality_check", "voice_tts", "music", "sfx"],
                 description="Merge rendered clips with audio via FFmpeg"),
    PipelineStage("telegram_delivery", "telegram-delivery", "19_telegram_delivery",
                 depends_on=["ffmpeg_assembly"],
                 description="Deliver final video and assets to Telegram"),
    PipelineStage("self_optimize", "self-optimize", "20_self_optimize",
                 depends_on=["ffmpeg_assembly"],
                 description="Collect metrics and optimize for future runs"),
]


class Pipeline:
    """Manages the pipeline DAG and execution order."""

    def __init__(self, stages: Optional[List[PipelineStage]] = None):
        self.stages = stages or PIPELINE_STAGES
        self._stage_map: Dict[str, PipelineStage] = {s.name: s for s in self.stages}

    def get_stage(self, name: str) -> Optional[PipelineStage]:
        return self._stage_map.get(name)

    def get_parallel_stages(self) -> List[PipelineStage]:
        return [s for s in self.stages if s.can_run_parallel]

    def get_stages_after(self, stage_name: str) -> List[PipelineStage]:
        result = []
        for s in self.stages:
            if stage_name in s.depends_on:
                result.append(s)
        return result

    def get_execution_order(self) -> List[List[str]]:
        """Return topological layers — stages that can run in the same batch."""
        resolved: set = set()
        layers: List[List[str]] = []
        remaining = list(self._stage_map.keys())

        while remaining:
            layer = []
            for name in remaining:
                stage = self._stage_map[name]
                if all(dep in resolved for dep in stage.depends_on):
                    layer.append(name)
            if not layer:
                raise ValueError(f"Circular dependency detected among: {remaining}")
            layers.append(layer)
            resolved.update(layer)
            remaining = [n for n in remaining if n not in resolved]

        return layers

    def total_stages(self) -> int:
        return len(self.stages)

    def validate_dependencies(self) -> bool:
        for stage in self.stages:
            for dep in stage.depends_on:
                if dep not in self._stage_map:
                    return False
        return True
