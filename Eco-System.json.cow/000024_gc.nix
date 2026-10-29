# modules/system/ops/gc.nix
{ config, pkgs, lib, ... }:

let
  retentionCfg = config.mySystem.ops.gc.retention;
  collectCfg = config.mySystem.ops.gc.collect;

  # ------------------------------------------------------------------
  # Binary: eco-gc-retention
  # ------------------------------------------------------------------
  ecoGcRetention = pkgs.writeShellApplication {
    name = "eco-gc-retention";
    runtimeInputs = with pkgs; [ python3 nix e2fsprogs ];
    text = ''
      exec python3 ${./gc-retention.py} \
        --keep-days ${toString retentionCfg.keepDays} \
        --min-generations ${toString retentionCfg.minGenerations} \
        --safety-hours ${toString retentionCfg.safetyHours} \
        --max-safety-generations ${toString retentionCfg.maxSafetyGenerations} \
        "$@"
    '';
  };

  # ------------------------------------------------------------------
  # Binary: eco-gc-collect
  # ------------------------------------------------------------------
  ecoGcCollect = pkgs.writeShellApplication {
    name = "eco-gc-collect";
    runtimeInputs = with pkgs; [ python3 nix coreutils ];
    text = ''
      exec python3 ${./gc-collect.py} \
        --start-percent ${toString collectCfg.startPercent} \
        --target-percent ${toString collectCfg.targetPercent} \
        --max-iterations ${toString collectCfg.maxIterations} \
        --path ${lib.escapeShellArg collectCfg.checkPath} \
        "$@"
    '';
  };

  scheduleMap = {
    daily  = "daily";
    weekly = "weekly";
  };

in
{
  config = lib.mkMerge [
    # ------------------------------------------------------------------
    # Retention: nur Binary, kein Service
    # ------------------------------------------------------------------
    (lib.mkIf retentionCfg.enable {
      environment.systemPackages = [ ecoGcRetention ];
    })

    # ------------------------------------------------------------------
    # Collect: Binary + Service + Timer
    # ------------------------------------------------------------------
    (lib.mkIf collectCfg.enable {
      environment.systemPackages = [ ecoGcCollect ];

      systemd.services.eco-gc-collect = {
        description = "eco-gc-collect — Nix-Store aufräumen bei Platzmangel";
        serviceConfig = {
          Type = "oneshot";
          Nice = 19;
          IOSchedulingClass = "idle";
          ExecStart = "${ecoGcCollect}/bin/eco-gc-collect";
          # Exit-Codes des Skripts:
          #   0 — Ziel erreicht oder nichts zu tun
          #   1 — echter Fehler (GC fehlgeschlagen)
          #   2 — Validierungsfehler
          #   3 — Ziel nicht erreicht, kein Fehler
          # Für systemd sind 0 und 3 erfolgreich. Fehler (1, 2) bleiben
          # sichtbar in `systemctl --failed`.
          SuccessExitStatus = "0 3";
        };
      };

      systemd.timers.eco-gc-collect = lib.mkIf (collectCfg.schedule != "never") {
        description = "Periodischer eco-gc-collect-Lauf";
        wantedBy = [ "timers.target" ];
        timerConfig = {
          OnCalendar = scheduleMap.${collectCfg.schedule};
          Persistent = true;
          RandomizedDelaySec = "1h";
          Unit = "eco-gc-collect.service";
        };
      };
    })
  ];
}
