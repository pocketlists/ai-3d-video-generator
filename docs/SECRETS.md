# GitHub Secrets — AI 3D Video Generator

## Required Secrets

These must be configured in your GitHub repository settings for the pipeline to function.

### TELEGRAM_BOT_TOKEN (Required)
Your Telegram Bot API token. Create a bot via [@BotFather](https://t.me/BotFather).

**How to get it:**
1. Open Telegram and message @BotFather
2. Send `/newbot` and follow instructions
3. Copy the token (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### TELEGRAM_CHANNEL_ID (Required)
The ID of the Telegram channel where videos will be delivered.

**How to get it:**
1. Create a Telegram channel
2. Add your bot as an administrator
3. Get the channel ID (starts with `-100` for channels, or use `@channelusername`)

## Optional Secrets

### OPENAI_API_KEY
For AI-powered video planning. Without this, the system uses template-based planning.

**Get it from:** https://platform.openai.com/api-keys

### ELEVENLABS_API_KEY
For high-quality text-to-speech voice generation.

**Get it from:** https://elevenlabs.io

### HF_TOKEN
HuggingFace token for accessing AI models.

**Get it from:** https://huggingface.co/settings/tokens

### REPLICATE_API_TOKEN
For AI asset generation via Replicate.

**Get it from:** https://replicate.com/account/api-tokens

## Adding Secrets to GitHub

1. Go to your repository on GitHub
2. Navigate to Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Enter the secret name and value
5. Click "Add secret"

## Security

- Secrets are never logged or printed
- Secrets are accessed via environment variables in workflows
- No credentials are hard-coded in the source code
- The `.gitignore` file excludes `.env` and `secrets.env` files
