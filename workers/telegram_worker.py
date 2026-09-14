"""
Telegram delivery worker — delivers final video and assets to Telegram.

Stage 19: Uploads the final video, key assets, and a summary to the
configured Telegram channel.
"""
import json
import os
from typing import Any, Dict, List

from workers.base_worker import BaseWorker
from utils.telegram_client import TelegramClient, TelegramError


class TelegramWorker(BaseWorker):
    stage_name = "telegram_delivery"

    def run(self) -> Dict[str, Any]:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")

        # Load final video path
        qc_report = self._load_json(os.path.join(artifact_dir, "quality_check_report.json"))
        final_video = os.path.join(artifact_dir, "output", "final_video.mp4")

        if not os.path.exists(final_video):
            return {"status": "error", "error": f"Final video not found: {final_video}"}

        try:
            client = TelegramClient()
        except TelegramError as e:
            self.logger.error(f"Telegram not configured: {e}")
            return {"status": "skipped", "reason": "Telegram not configured",
                    "error": str(e)}

        results = []

        # Send progress message
        try:
            msg = client.send_message(
                "🎬 *Video Generation Complete!*\n\nThe pipeline has finished rendering."
            )
            results.append({"type": "message", "success": True})
        except TelegramError as e:
            results.append({"type": "message", "success": False, "error": str(e)})

        # Send final video
        try:
            client.send_video(
                final_video,
                caption="🎬 Final rendered video",
                duration=int(qc_report.get("estimated_duration_sec", 60)),
                width=1280, height=720
            )
            results.append({"type": "video", "success": True})
        except TelegramError as e:
            self.logger.error(f"Video upload failed: {e}")
            results.append({"type": "video", "success": False, "error": str(e)})

        # Send key assets (scene plan, quality report)
        for asset_name in ["scene/scene_plan.json", "quality_check_report.json"]:
            asset_path = os.path.join(artifact_dir, asset_name)
            if os.path.exists(asset_path):
                try:
                    client.send_document(asset_path, caption=f"📎 {asset_name}")
                    results.append({"type": "document", "name": asset_name, "success": True})
                except TelegramError:
                    results.append({"type": "document", "name": asset_name, "success": False})

        # Send summary
        summary = self._build_summary(qc_report, results)
        try:
            client.send_message(summary)
            results.append({"type": "summary", "success": True})
        except TelegramError:
            results.append({"type": "summary", "success": False})

        success_count = sum(1 for r in results if r.get("success"))
        return {
            "status": "success" if success_count > 0 else "error",
            "results": results,
            "success_count": success_count,
            "total_count": len(results),
            "final_video_path": final_video,
        }

    def _load_json(self, path: str) -> Dict:
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _build_summary(self, qc: Dict, results: List) -> str:
        passed = qc.get("passed", "N/A")
        frames = qc.get("total_frames", "N/A")
        duration = qc.get("estimated_duration_sec", "N/A")
        issues = qc.get("issues", [])
        success = sum(1 for r in results if r.get("success"))

        text = (
            "📊 *Pipeline Summary*\n"
            f"Quality check: {'✅ Passed' if passed else '⚠️ Issues'}\n"
            f"Total frames: {frames}\n"
            f"Duration: {duration}s\n"
            f"Deliveries: {success}/{len(results)} successful\n"
        )
        if issues:
            text += f"Issues: {', '.join(issues[:3])}"
        return text
