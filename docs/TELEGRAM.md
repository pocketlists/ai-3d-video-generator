# Telegram Architecture

## Escalation (controller/telegram_escalation.py)

When a critical provider fails (after classified retries):

1. Checkpoint saved.
2. Escalation message sent with: JOB_ID, STAGE, PROVIDER, ERROR,
   EXPECTED_RESPONSE, RESUME_TOKEN, STATUS.
3. State = WAITING_FOR_EXTERNAL_RESPONSE.
4. Runner exits cleanly — NO waiting inside the runner (RULE 12).
   The system can wait 5 minutes or 5 days without a live runner.

The resume token is ALWAYS generated (even if Telegram delivery fails) —
it is the resume key for resume.yml, independent of delivery.

## Reply Parsing (PHASE 17)

All update types handled: normal message, reply to escalation, channel
post, reply to channel post, edited message/post, bot commands.
NEVER assumes only `update["message"]`.

Validated: chat_id, message_id, reply_to_message_id, job_id, resume_token,
authorized user.

## Security (PHASE 50)

Only users in TELEGRAM_ALLOWED_USER_IDS can resume/cancel/retry/override.
Unauthorized replies are rejected and logged (verified by
`TestTelegramEscalation.test_unauthorized_user_rejected`).
Arbitrary Telegram messages are never treated as pipeline commands.

## Delivery Gate (PHASE 79)

The final video is sent ONLY when: render complete AND all frames present
AND FFmpeg successful AND video readable AND audio valid AND QC passed.
Otherwise: NO final video — the job reports failure honestly.
Placeholder videos are never reported as success (RULE 15).

## Asset Archive (PHASE 49)

Telegram can receive character/environment/prop previews, audio, clips,
and the final video — with JOB_ID/TYPE/SHOT/VERSION captions. No useless
temporary files are sent.
