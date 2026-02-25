# URF825 Multimode Reflector — Installation Guide

This guide walks you through setting up a URF multimode reflector using Docker on a Linux server. It is written for users who are new to Linux and Docker.

The reflector supports D-Star, DMR, YSF, M17, NXDN, P25 and more — all running in Docker containers so no manual compilation or system-level installation is required.

---

## Prerequisites

You will need:

- A Linux server (Ubuntu 22.04 or 24.04 recommended) with a public IP address
- Your amateur radio callsign registered at [radioid.net](https://radioid.net)
- The following ports open in your firewall/router:

| Port | Protocol | Purpose |
|------|----------|---------|
| 80 | TCP | Dashboard web interface |
| 10017 | UDP | URF interlinking |
| 17000 | UDP | M17 |
| 20001 | UDP | DPlus (D-Star) |
| 30001 | UDP | DExtra (D-Star) |
| 30051 | UDP | DCS (D-Star) |
| 40000 | UDP | DSD |
| 41000 | UDP | P25 |
| 41400 | UDP | NXDN |
| 42000 | UDP | YSF |
| 62030 | UDP | MMDVM (DMR hotspots) |

---

## Step 1 — Install Docker

If Docker is not already installed, run the following commands:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

Add your user to the Docker group so you can run Docker without `sudo`:

```bash
sudo usermod -aG docker $USER
```

Then log out and back in for this to take effect.

---

## Step 2 — Install Git

```bash
sudo apt-get install -y git
```

---

## Step 3 — Clone the Repository

Clone the `docker` branch of the repository into a directory of your choice. A good location is `~/source`:

```bash
mkdir -p ~/source
cd ~/source
git clone -b docker https://github.com/mcdent/2urfd-g6phf.git 2urfd
cd 2urfd
```

---

## Step 4 — Configure the Reflector

All configuration files live in `docker/config/`. You need to edit four files before starting.

### 4a — `docker/config/urfd.ini` (main reflector settings)

Open the file in a text editor:

```bash
nano docker/config/urfd.ini
```

Change the following values to match your setup:

| Setting | What to change |
|---------|----------------|
| `Callsign` | Your URF callsign, e.g. `URF123` |
| `SysopEmail` | Your email address |
| `Country` | Your 2-letter country code, e.g. `GB` |
| `Sponsor` | Your callsign, e.g. `M0ABC` |
| `DashboardUrl` | The URL of your dashboard, e.g. `http://xlx.m0abc.co.uk` |
| `IPv4External` | Your server's **public** IP address |
| `Modules` | The modules you want active (letters A–Z, e.g. `ADMSZ`) |
| `ReflectorID` | Your reflector number, e.g. `123` (used by NXDN and P25) |
| `RegistrationID` | Your YSF registration ID, e.g. `00123` |
| `RegistrationName` | A short name for your YSF node |

Save with `Ctrl+O`, then `Enter`, then exit with `Ctrl+X`.

### 4b — `docker/config/dashboard-config.inc.php` (dashboard settings)

```bash
nano docker/config/dashboard-config.inc.php
```

Change the following:

| Setting | What to change |
|---------|----------------|
| `$PageOptions['ContactEmail']` | Your email address |
| `$PageOptions['ModuleNames']` | Descriptions for each module letter you enabled |
| `$CallingHome['MyDashBoardURL']` | Your dashboard's public URL |
| `$CallingHome['Country']` | Your 2-letter country code |
| `$CallingHome['Comment']` | A short description, e.g. `URF123 - M0ABC` |
| `$CallingHome['OverrideIPAddress']` | Your server's public IP address |
| `date_default_timezone_set(...)` | Your timezone, e.g. `Europe/London` |

> **Tip:** The `$PageOptions['ModuleNames']` section should list only the modules you enabled in `urfd.ini`. Remove or comment out any module lines that don't apply to you.

### 4c — `docker/config/urfd.whitelist` and `docker/config/urfd.blacklist`

These files control who can connect to your reflector.

- **Whitelist** — if you add callsigns here, *only* those callsigns will be allowed. Leave this file empty to allow everyone.
- **Blacklist** — add callsigns here to block specific users.

For a public reflector, leave both files empty. You do not need to edit them.

### 4d — `docker/config/urfd.interlink` (optional — peering with other reflectors)

This file lets you peer with other URF reflectors. Leave it empty for now. The format is documented inside the file itself if you want to add peers later.

---

## Step 5 — Start the Reflector

Move into the docker directory and bring up the containers:

```bash
cd ~/source/2urfd/docker
docker compose up -d
```

Docker will build the images on first run — this takes a few minutes. Once complete, check that everything is running:

```bash
docker compose ps
```

You should see two containers listed as `Up`:
- `urfd` — the reflector
- `urfd-dashboard` — the web dashboard

---

## Step 6 — Check the Logs

To watch the reflector log in real time:

```bash
docker logs -f urfd
```

You should see lines confirming each protocol has started. Press `Ctrl+C` to stop following the log.

---

## Step 7 — Open the Dashboard

Open a web browser and navigate to your server's IP address or hostname:

```
http://YOUR-SERVER-IP
```

You should see the reflector dashboard showing your callsign, active modules, and any connected stations.

---

## Stopping and Restarting

To stop the reflector:

```bash
cd ~/source/2urfd/docker
docker compose down
```

To restart after making config changes:

```bash
docker compose down
docker compose up -d
```

> **Note:** You do **not** need to rebuild the Docker images when you change config files — they are loaded at startup from the `docker/config/` directory.

---

## Transcoder (Optional — DVSI Hardware)

The transcoder (`tcd`) allows real-time audio conversion between modes (e.g. D-Star ↔ DMR). It requires a DVSI USB dongle (DV3000 or DV3003) connected to your server.

If you have one:

1. Edit `docker/config/tcd.ini` and set `Transcoded` to the module you want transcoded (e.g. `A`).
2. In `docker/config/urfd.ini`, uncomment the `[Transcoder]` section and set `Transcoded` to the same module.
3. In `docker/docker-compose.yml`, change `ENABLE_TCD=false` to `ENABLE_TCD=true`.
4. Restart the containers.

If you do not have DVSI hardware, leave everything as-is. The reflector works fine without transcoding.

---

## Keeping Up To Date

To pull the latest changes from the repository:

```bash
cd ~/source/2urfd
git pull
cd docker
docker compose down
docker compose up -d --build
```

The `--build` flag rebuilds the reflector image from the updated source code.

---

## Troubleshooting

**Dashboard shows nothing / reflector not reachable**
- Check that the UDP ports listed in the Prerequisites section are open on your firewall and router.
- Confirm `IPv4External` in `urfd.ini` matches your actual public IP.

**Container won't start**
- Run `docker logs urfd` to see error messages.
- Double-check that all required fields in `urfd.ini` have been filled in (no placeholder values).

**YSF not working**
- Make sure your `RegistrationID` in `urfd.ini` is a 5-digit zero-padded number matching your reflector number (e.g. `00123`).

**D-Star users can't connect**
- Ensure ports 20001, 30001 and 30051 are all open.

---

## Summary of Files to Edit

| File | Must edit | Purpose |
|------|-----------|---------|
| `docker/config/urfd.ini` | Yes | Callsign, IP, modules, protocols |
| `docker/config/dashboard-config.inc.php` | Yes | Dashboard appearance and calling-home |
| `docker/config/urfd.whitelist` | No | Restrict access to specific callsigns |
| `docker/config/urfd.blacklist` | No | Block specific callsigns |
| `docker/config/urfd.interlink` | No | Peer with other URF reflectors |
| `docker/config/tcd.ini` | No | Transcoder settings (DVSI hardware only) |
