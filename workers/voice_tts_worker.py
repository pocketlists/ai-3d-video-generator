"""
Voice TTS worker — generates voice-over narration via TTS.

Stage 11: Converts narration text to speech audio using available
TTS services (ElevenLabs, gTTS, or eSpeak as fallback).
"""
import json
import os
import subprocess
import tempfile
from typing import Any, Dict, List

from workers.base_worker import BaseWorker
from utils.retry import retry


class VoiceTTSWorker(BaseWorker):
    stage_name = "voice_tts"

    def run(self) -> Dict[str, Any]:
        breakdown = self._load_breakdown()
        if not breakdown:
            return {"status": "error", "error": "No breakdown found"}

        audio_files = self._generate_voice(breakdown)
        path = self._save_voice_manifest(audio_files)
        return {
            "status": "success",
            "voice_manifest_path": path,
            "audio_count": len(audio_files),
        }

    def _load_breakdown(self) -> Dict:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(artifact_dir, "script_breakdown.json")
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _generate_voice(self, breakdown: Dict) -> List[Dict]:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts/audio")
        os.makedirs(out_dir, exist_ok=True)
        audio_files = []

        for shot in breakdown.get("shots", []):
            narration = shot.get("narration", "").strip()
            if not narration:
                continue

            filename = f"voice_shot_{shot['scene_id']}.mp3"
            filepath = os.path.join(out_dir, filename)

            if self._try_elevenlabs(narration, filepath):
                source = "elevenlabs"
            elif self._try_gtts(narration, filepath):
                source = "gtts"
            elif self._try_espeak(narration, filepath):
                source = "espeak"
            else:
                self.logger.warning(f"No TTS available for shot {shot['scene_id']}")
                continue

            audio_files.append({
                "scene_id": shot["scene_id"],
                "text": narration,
                "filepath": filepath,
                "source": source,
                "frame_start": shot["frame_start"],
                "frame_end": shot["frame_end"],
            })
            self.logger.info(f"Generated voice for shot {shot['scene_id']} via {source}")

        return audio_files

    @retry(max_attempts=2, initial_delay=3.0)
    def _try_elevenlabs(self, text: str, output_path: str) -> bool:
        api_key = self.config.get("elevenlabs_api_key") or os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            return False
        try:
            import urllib.request
            voice_id = "21m00Tcm4TlvDq8ikWAM"
            payload = json.dumps({"text": text, "model_id": "eleven_multilingual_v2"}).encode()
            req = urllib.request.Request(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                data=payload,
                headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                with open(output_path, "wb") as f:
                    f.write(resp.read())
            return True
        except Exception as e:
            self.logger.debug(f"ElevenLabs TTS failed: {e}")
            return False

    @retry(max_attempts=2, initial_delay=2.0)
    def _try_gtts(self, text: str, output_path: str) -> bool:
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang="en", slow=False)
            tts.save(output_path)
            return True
        except ImportError:
            return False
        except Exception as e:
            self.logger.debug(f"gTTS failed: {e}")
            return False

    @retry(max_attempts=2, initial_delay=1.0)
    def _try_espeak(self, text: str, output_path: str) -> bool:
        try:
            result = subprocess.run(
                ["espeak", "-w", output_path.replace(".mp3", ".wav"), text],
                capture_output=True, timeout=15
            )
            if result.returncode == 0:
                return True
            return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _save_voice_manifest(self, audio_files: List[Dict]) -> str:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(out_dir, "voice_manifest.json")
        with open(path, "w") as f:
            json.dump(audio_files, f, indent=2)
        return path
