# Virginia Tech ARC quick start

SUGAR can use Virginia Tech ARC as its OpenAI-compatible LLM provider while SUGAR itself runs on the user's computer.

## Classroom setup

1. Open SUGAR **Settings**.
2. Choose **Get ARC API Key** to open `https://llm.arc.vt.edu`.
3. Sign in with Virginia Tech credentials.
4. Open **User profile → Settings → Account → API keys** and create a personal API key.
5. Paste the key into SUGAR's ARC/API-key field. Keep it private.
6. Choose **Virginia Tech ARC** and press **Test ARC Connection**.
7. Select an ARC model for AI-assisted workflows.

As checked against ARC documentation on 2026-09-17, the primary shared model IDs are:

- `gpt-oss-120b`
- `DeepSeek-V4.1-Flash`
- `GLM-5.3`
- `Kimi-K3`

The shared endpoint is `https://llm-api.arc.vt.edu/api/v1`. ARC documents the shared API as available to Virginia Tech students, faculty, and staff without a separate ARC account and with no individual charge for hosted-model API access. Model availability can change, so future releases should re-check ARC's current model documentation.

Dedicated Open OnDemand LLM sessions at `https://ood.arc.vt.edu` are different: they require an ARC account/allocation and consume service units.
