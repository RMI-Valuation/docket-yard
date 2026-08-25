# RMI-AI-MACHINE — Windows to Ubuntu Server conversion

Step-by-step conversion of the batch-enrichment box (i7-14700KF, RTX 4070 12GB, 64GB DDR5,
2× 2TB NVMe) from Windows 11 to headless Ubuntu Server. Written for someone who has never
installed Linux. The machine's role afterwards: the batch worker described in
[`../docs/architecture.md`](../docs/architecture.md) — LLM extraction, OCR, backfill
enrichment. It carries no uptime promise; nothing breaks if a step goes sideways.

**JetKVM note:** the JetKVM works below the operating system, so you keep remote screen,
keyboard, and BIOS access through the entire wipe and install. You can do everything below
from your desk. After setup, day-to-day access is SSH over Tailscale; the JetKVM becomes the
break-glass console.

**Point of no return:** step 3 erases Windows on the system drive. Before starting, copy
anything you want off the machine (check Desktop, Documents, Downloads, browser profiles).
Nothing else below is destructive to anything but that machine.

---

## 1. Prepare (on your daily machine)

1. Download **Ubuntu Server 24.04 LTS** (the "live server" ISO, ~3 GB) from
   `https://ubuntu.com/download/server`. Server, not Desktop: no GUI, which is what a
   headless box wants.
2. Download **Rufus** from `https://rufus.ie`. Insert a USB stick (8 GB+, will be erased).
3. In Rufus: select the USB stick, select the ISO, keep defaults (GPT / UEFI), press START.
   Accept the "write in ISO mode" default. Done in a few minutes.
   - *Alternative:* JetKVM can mount the ISO as virtual media over the network, which
     avoids the stick entirely — but a physical stick is faster and has fewer moving parts.
     Use virtual media only if walking a stick to the machine is a real inconvenience.

## 2. BIOS settings

Plug in the stick, reboot the machine, and tap **Del** (or F2) at the ASUS splash to enter
BIOS. Through JetKVM this works exactly as if you were seated at it.

1. **Disable Secure Boot** (Boot → Secure Boot → Other OS, on ASUS). Ubuntu itself supports
   Secure Boot, but the NVIDIA driver then needs a signing dance (MOK enrolment) that is
   pure friction on a headless box. Off is simpler and costs nothing here.
2. **Advanced → APM → Restore AC Power Loss → Power On.** After any outage the machine
   comes back by itself — on a headless server this is the setting everyone forgets.
3. Boot menu (F8 from BIOS, or set boot order): boot the USB stick, choosing the **UEFI**
   entry for it.

## 3. Install Ubuntu Server (~15 minutes)

The installer is text-based; arrow keys, Tab, Enter, Space to toggle. Choices, in the order
they appear:

1. Language / keyboard: as appropriate.
2. Installation type: **Ubuntu Server** (the default, not "minimized").
3. Network: plug the LAN cable into the **first** of the two 2.5GbE ports; it gets a DHCP
   address automatically. Note the IP it shows — you will SSH to it shortly.
4. Proxy: leave blank. Mirror: leave default.
5. Storage: **Use an entire disk** → pick the **Samsung 990 PRO** (both drives are 2TB;
   the 990 PRO is the newer/faster one and becomes the system disk; the 970 EVO Plus stays
   untouched for now and becomes the data disk in step 6). Keep the default LVM layout.
   Confirm — **this is the step that erases Windows.**
6. Profile: your name; server name `rmi-ai-machine`; a username; a strong password (it is
   also your sudo password).
7. Upgrade to Ubuntu Pro: skip.
8. **SSH: check "Install OpenSSH server."** Do not skip this — it is how you reach the
   machine ever after.
9. Featured snaps: select nothing.
10. Let it install, then "Reboot Now" (unplug the stick when prompted).

## 4. First login and basics

From your daily machine's terminal (PowerShell has ssh built in):

```sh
ssh <username>@<the-ip-from-step-3.3>
```

Then, on the machine:

```sh
sudo apt update && sudo apt full-upgrade -y     # patch everything
sudo timedatectl set-timezone America/Chicago   # adjust to taste
sudo reboot
```

Ubuntu Server applies security patches automatically (unattended-upgrades is on by
default). Leave that alone.

## 5. Tailscale (makes the IP and location irrelevant)

On the machine:

```sh
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh
```

It prints a URL — open it on your daily machine and log in to your tailnet. Install
Tailscale on your daily machine too, if it is not already. From then on:

```sh
ssh <username>@rmi-ai-machine    # from anywhere on the tailnet, any network
```

`--ssh` enables Tailscale SSH (auth via the tailnet, keys managed for you). The machine
needs **no ports forwarded and nothing exposed to the internet** — do not create any.

## 6. The data disk (the 970 EVO Plus)

```sh
lsblk                                   # identify the empty 2TB disk, e.g. nvme1n1 — the
                                        # one with no partitions; the system disk shows /
sudo mkfs.ext4 -L data /dev/nvme1n1     # erases that disk; double-check the name first
sudo mkdir /data
echo 'LABEL=data /data ext4 defaults,nofail 0 2' | sudo tee -a /etc/fstab
sudo mount -a && df -h /data            # should show ~1.8T free
sudo chown $USER:$USER /data
```

`/data` holds model weights, work batches, and blob caches. Like the repo's `data/`, treat
it as rebuildable.

## 7. NVIDIA driver + Docker

```sh
# NVIDIA driver (headless server variant, auto-selected):
sudo ubuntu-drivers install --gpgpu
# --gpgpu installs the kernel driver only (nvidia-headless-NNN-server); nvidia-smi lives in
# nvidia-utils, which it does NOT pull in. Install the matching version before rebooting:
dpkg -l | grep nvidia-headless          # note the version, e.g. 580-server
sudo apt install nvidia-utils-580-server   # use the version you just saw
sudo reboot
# after reconnecting:
nvidia-smi                              # success = a table showing "NVIDIA GeForce RTX 4070"
# "command not found" = nvidia-utils missing (step above); "couldn't communicate with the
# NVIDIA driver" = module not loaded — check `lsmod | grep nvidia`, reboot again.

# Docker Engine (Docker's official repo — Ubuntu's docker.io also works, this stays current):
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER           # log out and back in for this to take effect

# NVIDIA container toolkit (GPU inside containers):
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker

# verify GPU-in-Docker:
docker run --rm --gpus all ubuntu nvidia-smi
```

## 8. First model

```sh
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:14b                   # ~9 GB; fits the 4070 fully
ollama run qwen3:14b "Reply with the single word: ready"
```

`nvidia-smi` in a second SSH session should show the model resident in GPU memory while it
answers. Larger MoE-class models via llama.cpp come later, when the enrichment work defines
what is actually needed — see the benchmark item parked in `TODO.md`.

## 9. What NOT to do on this machine

- **No self-hosted GitHub Actions runner** for the public repo — fork PRs could execute
  code here. This is recorded in `TODO.md` and it is permanent.
- **No port forwarding, no public exposure.** Tailscale is the only way in; JetKVM is the
  console fallback.
- **No secrets at rest.** Work credentials arrive scoped and short-lived when the
  enrichment loop is built, per the runbook's secrets rules.
- **No promise-bearing duties.** If something must not miss a beat, it belongs on the
  cloud box (`../docs/architecture.md`). This machine is allowed to be off.

## Done when

`ssh rmi-ai-machine` works from the tailnet, `nvidia-smi` shows the 4070, `docker run --rm
--gpus all ubuntu nvidia-smi` works, `/data` is mounted, a 14B model answers, and the BIOS
restores power after an outage (pull the plug once to prove it).
