# Hermes + Hindsight stack

One folder, two services, one compose file:

- **Hindsight (`hindsight`)**: long-term memory. Its API runs on `127.0.0.1:8888`, and its web UI on `127.0.0.1:9999`. Its MCP endpoint is `/mcp/<bank>/`, and this stack uses the bank `hermes`. Its LLM is NVIDIA NIM.
- **Hermes Agent (`hermes`)**: the official Docker image. Its API runs on `127.0.0.1:8642`, and its dashboard on `127.0.0.1:9119`. Hermes reads and writes the Hindsight memory through MCP.

```
Hermes Agent  --MCP-->  hindsight  http://hindsight:8888/mcp/hermes/   (retain, recall, reflect)
     |
     +-- API on http://127.0.0.1:8642  (chat, from this PC)
```

Everything binds to `127.0.0.1`, so only this PC can reach it. Cognee was removed from this PC. The live server is separate and was not changed.

## What you need

- Docker Desktop, running.
- One NVIDIA NIM API key (`nvapi-...`) from build.nvidia.com. It goes in `.env` as `NVIDIA_API_KEY`. Hindsight and Hermes both use it.
- Python on this PC, only if you want to run `smoke_test.py`.

## Files

| File | Purpose |
|---|---|
| `compose.yaml` | The one Docker file. Runs Hindsight and Hermes together. |
| `.env.example` | Settings template. Copy it to `.env` and fill it in. |
| `smoke_test.py` | Checks the Hindsight tools, Hermes health and key, and optionally memory and chat. |
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
- Replace `nvapi-YOUR_NVIDIA_API_KEY` with your NVIDIA key in `NVIDIA_API_KEY`.
- Set `HERMES_DASHBOARD_PASSWORD` and `HERMES_DASHBOARD_SECRET` to new random values, using the same command.

## 2. Start the stack

```powershell
docker compose up -d --wait
docker compose ps
```

Both services should show `Up`. Hindsight takes about a minute to start.

## 3. Set Hermes to NVIDIA

These settings are already applied in this folder's Hermes data. Run them again only after a reset:

```powershell
docker compose exec hermes hermes config set model.provider nvidia
docker compose exec hermes hermes config set model.default nvidia/nemotron-3-ultra-550b-a55b
docker compose restart hermes
```

## 4. Link Hermes to Hindsight

This is already done in this folder. Run it again only after a reset:

```powershell
docker compose exec hermes hermes mcp remove shared-memory
docker compose exec hermes hermes config set mcp_servers.hindsight.url http://hindsight:8888/mcp/hermes/
docker compose exec hermes hermes mcp test hindsight
docker compose restart hermes
```

The test should report `Connected` and list about 36 tools, including `retain` and `recall`.

## 5. Test the stack

Run this once on this PC to install the test libraries:

```powershell
pip install mcp httpx
```

Then:

```powershell
python smoke_test.py
python smoke_test.py --memory
python smoke_test.py --chat
```

- The first command checks the Hindsight tools and Hermes.
- The second saves a marker with `retain` and looks for it with `recall`. A "marker not found yet" warning can mean Hindsight is still indexing the note, so run it again in a minute.
- The third sends one message to Hermes.

To test the whole path through Hermes, ask it in the dashboard or with `docker compose exec -it hermes hermes chat` to store a fact, then ask for it back in a new chat.

## Web pages

- **Hermes dashboard:** http://127.0.0.1:9119 (username `hermes-admin`, password in `.env` as `HERMES_DASHBOARD_PASSWORD`). Show the password with:

  ```powershell
  Select-String -Path .env -Pattern '^HERMES_DASHBOARD_PASSWORD='
  ```

- **Hindsight UI:** http://127.0.0.1:9999. It asks for a sign-in key first. Enter the value of `HINDSIGHT_CP_ACCESS_KEY` from `.env`. Show it in PowerShell with:

  ```powershell
  Select-String -Path .env -Pattern '^HINDSIGHT_CP_ACCESS_KEY='
  ```

  The key is shared by everyone who uses this UI on this PC. Change it in `.env` and run `docker compose up -d` if you need a new one.
- **Hindsight API:** http://127.0.0.1:8888 (health at `/health`). It has no sign-in, because Hermes uses it directly. It only answers on this PC.

## Everyday commands

```powershell
docker compose ps                     # status
docker compose logs -f hindsight      # live log for Hindsight
docker compose logs -f hermes         # live log for Hermes
docker compose restart hermes         # after changing .env or Hermes settings
docker compose up -d                  # apply .env changes
docker compose down                   # stop (keeps the memory and Hermes settings)
```

`docker compose down -v` deletes the Hindsight memory and all Hermes settings. Only run it if you want to start over.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `port is already allocated` (8888, 9999, 8642 or 9119) | Something else uses the port. Close it, then `docker compose up -d` again. |
| `Set NVIDIA_API_KEY in the .env file first` | Create `.env` (step 1) and set the key. |
| Hindsight log shows `401` or `Incorrect API key` | Replace `nvapi-YOUR_NVIDIA_API_KEY` in `NVIDIA_API_KEY`, then `docker compose up -d`. |
| `hermes mcp test hindsight` fails | Check `docker compose ps` shows `hindsight` up, then repeat step 4. |
| Hermes answers without using memory | Watch `docker compose logs -f hermes` for tool calls. Without them, the answer is not proof. |
| Dashboard asks for a login you don't have | Use `hermes-admin` and the password in `.env` (`HERMES_DASHBOARD_PASSWORD`). |
| Chat says `not connected to any AI provider` | Check `NVIDIA_API_KEY` in `.env`, then `docker compose up -d` and step 3. |

## Security

- Every port is bound to `127.0.0.1`. Only this PC can reach them.
- Hindsight's API and MCP have no login in this setup. Anyone who can reach `127.0.0.1:8888` can use the memory.
- The Hermes key gives access to the agent. Hermes can run commands inside its container, so keep the key private.
- Anything saved to memory is sent to NVIDIA for processing. Do not save passwords, API keys or card numbers.
- `.env` holds your keys. Do not share or commit it.
