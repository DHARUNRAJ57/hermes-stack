# Hermes + Cognee stack

One folder, two services, one compose file:

- **Cognee (`cognee-mcp`)**: shared memory. Its MCP server offers `remember`, `recall` and `forget`.
- **Hermes Agent (`hermes`)**: the official Docker image. Its API runs on `127.0.0.1:8642`. Hermes reads and writes the same Cognee memory.

```
Hermes Agent  --MCP-->  cognee-mcp (shared memory)  <--MCP--  any MCP client on this PC
     |
     +-- API on http://127.0.0.1:8642  (chat, from this PC)
```

Both services use NVIDIA NIM for the LLM and the embeddings. The ports are bound to `127.0.0.1`, so only this PC can reach them.

## What you need

- Docker Desktop, running.
- One NVIDIA NIM API key (`nvapi-...`) from build.nvidia.com. It goes into `.env` in three places (see step 1).
- Python on this PC, only if you want to run `smoke_test.py`.

## Files

| File | Purpose |
|---|---|
| `compose.yaml` | The one Docker file. Runs Cognee and Hermes together. |
| `.env.example` | Settings template. Copy it to `.env` and fill it in. |
| `smoke_test.py` | Checks the memory tools, Hermes health and key, and optionally memory and chat. |
| `.gitignore` | Keeps `.env` out of git. |

## 1. Create the .env file

```powershell
cd U:\office\personal-agent\hermes-stack
Copy-Item .env.example .env
```

Generate a random Hermes key and copy the output:

```powershell
$b = New-Object byte[] 32; (New-Object System.Security.Cryptography.RNGCryptoServiceProvider).GetBytes($b); -join ($b | ForEach-Object { '{0:x2}' -f $_ })
```

Open `.env`:

```powershell
notepad .env
```

- Paste the value as `HERMES_API_KEY`.
- Replace `nvapi-YOUR_NVIDIA_API_KEY` with your NVIDIA key in `LLM_API_KEY`, `NVIDIA_API_KEY` and `EMBEDDING_API_KEY`. It's the same key in all three.

## 2. Start the stack

```powershell
docker compose up -d --wait
docker compose ps
```

Both services should show `healthy`. Cognee's first start takes a few minutes, because it runs its database setup.

## 3. Set Hermes to NVIDIA

These settings are already applied in this folder's Hermes data. You only need to run them again if you reset the Hermes volume:

```powershell
docker compose exec hermes hermes config set model.provider nvidia
docker compose exec hermes hermes config set model.default nvidia/nemotron-3-ultra-550b-a55b
docker compose restart hermes
```

Hermes reads `NVIDIA_API_KEY` from `.env`. Chat answers need your real key in `.env` first.

## 4. Link Hermes to the shared memory

This gives Hermes the same Cognee memory the other clients use. It's already done in this folder. Run it again only after a reset:

```powershell
docker compose exec hermes hermes config set mcp_servers.shared-memory.url http://cognee-mcp:8000/mcp
docker compose exec hermes hermes mcp test shared-memory
docker compose restart hermes
```

The test should report `Connected` and list 6 tools, including `remember`, `recall` and `forget`.

## 5. Test the stack

Run this once on this PC to install the test libraries:

```powershell
pip install mcp httpx
```

Then:

```powershell
python smoke_test.py
```

Every check should show `PASS`. To also test the LLM-dependent parts, which need your real NVIDIA key:

```powershell
python smoke_test.py --chat
python smoke_test.py --memory
```

## Web dashboard

Hermes has a web dashboard, and this stack runs it on this PC only.

- **Open:** http://127.0.0.1:9119
- **Username:** `hermes-admin`
- **Password:** in `.env`, on the line `HERMES_DASHBOARD_PASSWORD`. To show it in PowerShell:

```powershell
Select-String -Path .env -Pattern '^HERMES_DASHBOARD_PASSWORD='
```

Sign in with the username and password. The dashboard is for this PC only. Do not publish port 9119 to your network or the internet. Hermes's own docs say the dashboard is not meant for public exposure.
## Everyday commands

```powershell
docker compose ps                     # status
docker compose logs -f hermes         # live log for Hermes
docker compose restart hermes         # after changing .env or Hermes settings
docker compose up -d                  # apply .env changes (recreates the services that changed)
docker compose down                   # stop (keeps the memory and Hermes settings)
```

`docker compose down -v` deletes the shared memory and all Hermes settings, including the LLM and memory settings. Only run it if you want to start over.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `port is already allocated` (8001 or 8642) | Something else uses the port. Close it, then `docker compose up -d` again. |
| `Set HERMES_API_KEY in the .env file first` | Create `.env` (step 1) and set the key. |
| `401` or `Incorrect API key` from NVIDIA | Replace `nvapi-YOUR_NVIDIA_API_KEY` in `LLM_API_KEY`, `NVIDIA_API_KEY` and `EMBEDDING_API_KEY`, then run `docker compose up -d`. |
| `421 Misdirected Request` from `cognee-mcp` | A host name is missing from `MCP_ALLOWED_HOSTS` in `compose.yaml`. Add it there. |
| `Hermes could not answer` or `not connected to any AI provider` | Check `NVIDIA_API_KEY` in `.env`, then `docker compose up -d` and step 3. |
| Vector size or dimension error after changing `EMBEDDING_DIMENSIONS` | Memory saved with the old size cannot be used with the new one. Ask before resetting, because a reset deletes the shared memory. |
| `Setting dimensions is not supported` when saving memory | The embedding model name must start with `nvidia_nim/` (set in `.env` as in the template). Then run `docker compose up -d`. |
| Dashboard: `Username and password required` or redirects to `/login` | Use `hermes-admin` and the password in `.env` (`HERMES_DASHBOARD_PASSWORD`). |
| `hermes mcp test shared-memory` fails | Check that `cognee-mcp` is healthy (`docker compose ps`), then repeat step 4. |

## Security

- Every port is bound to `127.0.0.1`. Only this PC can reach them.
- `cognee-mcp` has no login. Anyone who can reach `127.0.0.1:8001` can use the memory tools.
- The Hermes key gives access to the agent. Hermes can run commands inside its container, so keep the key private.
- Do not save passwords, API keys or card numbers to memory. Anything saved with `remember` is sent to NVIDIA for processing.
- `.env` holds your keys. Do not share or commit it.
