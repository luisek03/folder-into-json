# modules/system/ops/common.nix
{ config, lib, ... }:

{
  options.mySystem.ops = {
    update = {
      enable = lib.mkOption {
        type = lib.types.bool;
        default = false;
      };

      retries = lib.mkOption {
        type = lib.types.int;
        default = 0;
        description = "Max retries per step (0 = infinite).";
      };

      retryDelay = lib.mkOption {
        type = lib.types.int;
        default = 10;
      };

      cacheCheck = {
        enable = lib.mkOption {
          type = lib.types.bool;
          default = true;
          description = ''
            Cache-Check vor Kernel-Update aktivieren.
            Prüft, ob der aktive Kernel in den angegebenen Caches liegt.
          '';
        };

        # Wird vom aktiven Kernel-Modul gesetzt (z. B. chaotic.nix).
        # Leer bedeutet: kein Cache wird geprüft, der Check wird
        # übersprungen. Nur Kernel-Module, die tatsächlich einen
        # Cache haben, setzen hier etwas.
        caches = lib.mkOption {
          type = lib.types.listOf lib.types.str;
          default = [];
          description = ''
            Caches, in denen der aktive Kernel gesucht wird.
            Wird vom jeweiligen Kernel-Modul gesetzt.
          '';
        };
      };

      flakeLockBackup = {
        enable = lib.mkOption { type = lib.types.bool; default = false; };
        repoPath = lib.mkOption {
          type = lib.types.str;
          default = config.mySystem.paths.repo;
          defaultText = lib.literalExpression "config.mySystem.paths.repo";
        };
        autoCommit = lib.mkOption { type = lib.types.bool; default = false; };
        commitMessage = lib.mkOption {
          type = lib.types.str;
          default = "eco-update: flake.lock für %HOST% (%DATE%)";
        };
        gitAuthorName = lib.mkOption {
          type = lib.types.str;
          default = config.mySystem.userFullName;
        };
        gitAuthorEmail = lib.mkOption {
          type = lib.types.str;
          default = "${config.mySystem.userName}@localhost";
        };
      };

      # Post-Update-Hook: Shell-String, wird per bash -c ausgeführt.
      # Kann mehrere Befehle enthalten (&&, ;, |).
      postUpdate = {
        enable = lib.mkOption { type = lib.types.bool; default = false; };
        script = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = null;
          description = ''
            Shell-Befehl nach erfolgreichem switch.
            Beispiel: "eco-gc-retention"
            Beispiel: "eco-gc-retention && notify-send 'GC done'"
          '';
        };
      };
    };

    gc = {
      # ------------------------------------------------------------------
      # Teil 1: Retention
      # ------------------------------------------------------------------
      # Stellt nur das Binary `eco-gc-retention` bereit.
      # Kein systemd-Service, keine Path-Unit.
      # Wird typischerweise als postUpdate-Hook von eco-update aufgerufen.
      retention = {
        enable = lib.mkOption {
          type = lib.types.bool;
          default = false;
          description = ''
            Stellt eco-gc-retention bereit.
            Wird normalerweise per mySystem.ops.update.postUpdate.script
            als Hook aufgerufen.
          '';
        };

        keepDays = lib.mkOption {
          type = lib.types.int;
          default = 7;
        };

        minGenerations = lib.mkOption {
          type = lib.types.int;
          default = 4;
        };

        safetyHours = lib.mkOption {
          type = lib.types.int;
          default = 24;
          description = ''
            Generationen der letzten N Stunden werden immer behalten,
            unabhängig von Kalendertagen.

            Schützt späte Abend-Builds davor, nach Mitternacht aus dem
            Keep-Day-Fenster zu fallen. Setze 0, um die Regel zu deaktivieren
            (dann greift nur noch keepDays).
          '';
        };

        maxSafetyGenerations = lib.mkOption {
          type = lib.types.int;
          default = 20;
          description = ''
            Obergrenze für Generationen aus dem Safety-Fenster.

            Nach dem Safety-Filter werden nur die N neuesten Generationen
            behalten. Der Rest fällt aus dem Safety-Set, kann aber durch
            andere Regeln (rule_current, rule_keep_day, rule_floor)
            weiterhin geschützt sein.

            Sinn: Verhindert, dass ein einziger Deploy-Tag mit vielen
            Builds den Bootloader flutet. Der Wert sollte so gewählt sein,
            dass er selten erreicht wird — sonst greift der Cap ständig.

            Setze 0, um den Cap zu deaktivieren (unbegrenzt).
          '';
        };
      };

      # ------------------------------------------------------------------
      # Teil 2: Collect
      # ------------------------------------------------------------------
      # Stellt Binary `eco-gc-collect` + systemd-Service + systemd-Timer
      # bereit. Der Service entscheidet selbst, ob Speicher voll genug ist.
      # Kein Path-Unit, kein Rebuild-Trigger.
      collect = {
        enable = lib.mkOption {
          type = lib.types.bool;
          default = false;
        };

        startPercent = lib.mkOption {
          type = lib.types.int;
          default = 85;
          description = "Ab dieser Auslastung wird GC gestartet.";
        };

        targetPercent = lib.mkOption {
          type = lib.types.int;
          default = 80;
          description = "Bis zu dieser Auslastung wird GC laufen gelassen.";
        };

        maxIterations = lib.mkOption {
          type = lib.types.int;
          default = 3;
          description = ''
            Maximale GC-Läufe hintereinander. Danach wird abgebrochen,
            auch wenn target nicht erreicht (Speicher könnte durch
            andere Dinge voll sein).
          '';
        };

        checkPath = lib.mkOption {
          type = lib.types.str;
          default = "/nix/store";
          description = "Pfad, dessen Partition geprüft wird.";
        };

        schedule = lib.mkOption {
          type = lib.types.enum [ "daily" "weekly" "never" ];
          default = "daily";
          description = ''
            systemd-Timer-Intervall.
            "never" deaktiviert den Timer — Collect läuft dann nur manuell.
          '';
        };
      };
    };
  };
}
