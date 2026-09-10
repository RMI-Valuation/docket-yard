<#
The workstation's gate: the fleet may use this machine only while nobody is (docs/compute-fleet.md
§ Joining a node). A loop that, every 30 s, reads how long since the last keyboard or mouse
input and decides:

    idle for --IdleMinutes (default 10), no off switch   -> START: the vLLM container, then a
                                                            worker against the node's queue
    any input, or the off switch                         -> STOP: the worker first (it releases
                                                            its pages at once), then the container
                                                            (its VRAM comes back to the person)

The switches are files in ~/.docketyard: `fleet-off` (never run, whatever the idle time) and
`fleet-on` (run now, idle or not). The node's address is the one line in `fleet-node` there,
beside `fleet.token`; neither enters the repository, which is public. The worker's stop is a
file too (`fleet-stop`), which the worker checks before each page and instead of waiting for
a server; it is written at STOP and removed at START. STOP writes it, stops the container
(which ends any page in flight), and the worker is gone within seconds, its pages released.

    powershell -ExecutionPolicy Bypass -File tools\fleet\workstation-gate.ps1          # in a window
    # or once, as a task that starts at logon and keeps running:
    schtasks /Create /TN "Docket Yard fleet gate" /SC ONLOGON /RL LIMITED /TR ^
      "powershell -WindowStyle Hidden -ExecutionPolicy Bypass -File E:\DevProjects\docket-yard\tools\fleet\workstation-gate.ps1"

The container is the same vLLM image and version the node runs (0.28.0), with the same flags
plus VLLM_USE_V2_MODEL_RUNNER=0 — the V2 runner needs unified virtual addressing, which WSL2
does not offer; the V1 runner reads the same pages to the same text (11 of 12 identical, one
a character apart, measured 2026-09-09). The worker's producer declaration therefore matches
the pass and the queue accepts it (ADR 0023). The model is cached on a named volume; the first
start pulls ~6 GB. Several workers run at once because one request at a time is bound by
per-step overhead, not the card: the 5080 holds ten 16k requests in its KV cache. A hard stop
while pages are in flight costs their leases, nothing else: the lease makes this free.
#>
param(
    [int]$IdleMinutes = 10,
    [int]$Workers = 6,     # concurrent requests: measured 2026-09-09, 1 -> 11.2 s/page, 6 -> 3.3 s/page effective
    [string]$Node = "",   # default: the one line in ~/.docketyard/fleet-node, e.g. http://<node>:8131
    [string]$Repo = "E:\DevProjects\docket-yard",
    [string]$Container = "dots-vllm",
    [string]$Image = "vllm/vllm-openai:v0.28.0"
)

$ErrorActionPreference = "Continue"
$home_ = [Environment]::GetFolderPath("UserProfile")
$dir = Join-Path $home_ ".docketyard"
New-Item -ItemType Directory -Force $dir | Out-Null
$off = Join-Path $dir "fleet-off"
$on = Join-Path $dir "fleet-on"
$stop = Join-Path $dir "fleet-stop"
$token = Join-Path $dir "fleet.token"
$log = Join-Path $dir "fleet-gate.log"
$scratch = Join-Path $dir "render"
$python = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not $Node) { $Node = (Get-Content (Join-Path $dir "fleet-node") -ErrorAction Stop).Trim() }
$worker = Join-Path $Repo "tools\fleet\dots_worker.py"

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Idle {
    [StructLayout(LayoutKind.Sequential)] struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
    [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
    public static double Seconds() {
        var info = new LASTINPUTINFO(); info.cbSize = (uint)Marshal.SizeOf(info);
        GetLastInputInfo(ref info);
        return (Environment.TickCount - (int)info.dwTime) / 1000.0;
    }
}
"@

function Log($msg) { "$(Get-Date -Format s) $msg" | Tee-Object -FilePath $log -Append | Out-Null }

function ContainerRunning { (docker inspect -f "{{.State.Running}}" $Container 2>$null) -eq "true" }

function StartContainer {
    if (ContainerRunning) { return }
    $exists = docker inspect $Container 2>$null
    if ($exists) { docker start $Container | Out-Null; Log "container started"; return }
    docker run -d --name $Container --gpus all -p 8120:8000 `
        -v dots-hf-cache:/root/.cache/huggingface `
        -e VLLM_USE_FLASHINFER_SAMPLER=0 -e VLLM_USE_V2_MODEL_RUNNER=0 `
        -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True `
        $Image rednote-hilab/dots.mocr `
        --served-model-name dots-mocr --trust-remote-code `
        --chat-template-content-format string `
        --gpu-memory-utilization 0.90 --max-model-len 16384 | Out-Null
    Log "container created and started"
}

function StopContainer { if (ContainerRunning) { docker stop -t 20 $Container | Out-Null; Log "container stopped" } }

$script:procs = @{}   # worker index -> process
function Running($i) { $script:procs[$i] -and -not $script:procs[$i].HasExited }
function AnyRunning { foreach ($i in $script:procs.Keys) { if (Running $i) { return $true } }; $false }

function StartWorkers {
    Remove-Item -Force $stop -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force $scratch | Out-Null
    for ($i = 1; $i -le $Workers; $i++) {
        if (Running $i) { continue }
        $name = "$env:COMPUTERNAME/dots-$i"
        $args = @($worker, "--queue", $Node, "--token-file", $token, "--scratch", $scratch,
                  "--server", "http://127.0.0.1:8120/v1", "--stop-file", $stop, "--server-wait", "900",
                  "--name", $name)
        $script:procs[$i] = Start-Process -FilePath $python -ArgumentList $args -NoNewWindow -PassThru `
            -RedirectStandardOutput (Join-Path $dir "dots-worker-$i.log") `
            -RedirectStandardError (Join-Path $dir "dots-worker-$i.err")
        Log "worker $i started (pid $($script:procs[$i].Id))"
    }
}

function StopAll {
    New-Item -ItemType File -Force $stop | Out-Null   # the worker releases its pages and exits
    StopContainer                                     # ends the pages in flight, if any
    foreach ($i in @($script:procs.Keys)) {
        if (Running $i) {
            if (-not $script:procs[$i].WaitForExit(60000)) {
                $script:procs[$i].Kill(); Log "worker $i killed after 60 s; its leased pages return on expiry"
            } else { Log "worker $i stopped (exit $($script:procs[$i].ExitCode))" }
        }
    }
    $script:procs = @{}
}

Log "gate up: idle threshold $IdleMinutes min; switches in $dir"
$running = $false
while ($true) {
    $idle = [Idle]::Seconds()
    $wantOn = ((Test-Path $on) -or ($idle -ge $IdleMinutes * 60)) -and -not (Test-Path $off)
    if ($wantOn -and -not $running) {
        Log ("START: idle {0:n0} s" -f $idle)
        StartContainer; StartWorkers; $running = $true
    } elseif (-not $wantOn -and $running) {
        Log ("STOP: idle {0:n0} s, off switch {1}" -f $idle, (Test-Path $off))
        StopAll; $running = $false
    } elseif ($running -and -not (AnyRunning)) {
        # workers exit on their own when the queue is empty (0) or the server is gone (2..5);
        # they are started again a minute later — this branch's sleep plus the loop's — as
        # the node's loop does. $wantOn holds here: the branch above handles its other value
        Start-Sleep -Seconds 30
        StartWorkers
    }
    Start-Sleep -Seconds 30
}
