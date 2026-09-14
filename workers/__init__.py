"""Workers package — contains all 20 pipeline stage workers.

WORKER_REGISTRY maps stage names to worker classes for the orchestrator.
"""
from workers.base_worker import BaseWorker
from workers.planning_worker import PlanningWorker
from workers.script_worker import ScriptWorker
from workers.asset_worker import AssetWorker
from workers.character_worker import CharacterWorker
from workers.environment_worker import EnvironmentWorker
from workers.prop_worker import PropWorker
from workers.animation_worker import AnimationWorker
from workers.camera_worker import CameraWorker
from workers.lighting_worker import LightingWorker
from workers.voice_tts_worker import VoiceTTSWorker
from workers.music_worker import MusicWorker
from workers.sfx_worker import SFXWorker
from workers.lip_sync_worker import LipSyncWorker
from workers.blender_assembly_worker import BlenderAssemblyWorker
from workers.render_worker import RenderWorker
from workers.quality_check_worker import QualityCheckWorker
from workers.ffmpeg_worker import FFmpegWorker
from workers.telegram_worker import TelegramWorker
from workers.optimization_worker import OptimizationWorker

WORKER_REGISTRY = {
    "receive_request": PlanningWorker,  # stage 1 reuses planning for initial intake
    "ai_planning": PlanningWorker,
    "script_breakdown": ScriptWorker,
    "asset_collection": AssetWorker,
    "characters": CharacterWorker,
    "environments": EnvironmentWorker,
    "props": PropWorker,
    "animation": AnimationWorker,
    "camera": CameraWorker,
    "lighting": LightingWorker,
    "voice_tts": VoiceTTSWorker,
    "music": MusicWorker,
    "sfx": SFXWorker,
    "lip_sync": LipSyncWorker,
    "blender_assembly": BlenderAssemblyWorker,
    "render_workers": RenderWorker,
    "quality_check": QualityCheckWorker,
    "ffmpeg_assembly": FFmpegWorker,
    "telegram_delivery": TelegramWorker,
    "self_optimize": OptimizationWorker,
}
