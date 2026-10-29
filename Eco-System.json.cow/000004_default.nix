# /etc/nixos/hosts/laptop/init.nix
# ==========================================
# LAPTOP-SPEZIFISCHE KONFIGURATION
# ==========================================
# Dieses Modul enthält alle Einstellungen, die NUR auf dem Laptop gelten.
# Alles, was auch auf dem Desktop gelten soll, gehört nach common/default.nix.
# ==========================================

{ config, pkgs, lib, ... }:

{
  # ==========================================
  # IMPORT
  # ==========================================

  imports = [
    ../../profile/base
    ../../profile/luis-eco

    ./state-version.nix # unfassbar wichtig, nach jeder neuinstalltion von nixos entscheiden ob wert mit updaten
    ./fstab.nix
    ./kernel-modules.nix
    ./wifi-hardware.nix
    ../../modules/userland/nixos_ide.nix
    ../../modules/userland/games/steam.nix
    ../../modules/system/zram-swap.nix
  ];

  #systemd.services.polkit.restartIfChanged          = false;
  #systemd.services.accounts-daemon.restartIfChanged = false;

  # ==========================================
  # HOSTNAME
  # ==========================================
  # Überschreibt den Standard-Hostnamen aus common/default.nix.
  # So erkennst du im Netzwerk, welches Gerät der Laptop ist.
  # ==========================================
  networking.hostName = "Luis-Laptop";

  # ==========================================
  # NIX-BUILD — gezielte Laptop-Overrides
  # ==========================================
  # Aktuell keine Abweichung nötig. Wenn du später einen
  # einzelnen Key überschreiben willst, Punkt-Notation nutzen:
  #
  #   nix.settings.max-jobs = lib.mkForce 2;   # Laptop: nur 2 Jobs
  #   nix.settings.cores    = 0;
  #
  # (kein Block nix.settings = { }; — das würde die Basis-Definition
  #  komplett überschreiben, auch wenn der Block leer wirkt.)
  # ==========================================

  # ==========================================
  # BLUETOOTH
  # ==========================================
  # Nur auf dem Laptop sinnvoll – der Desktop hat meist kein Bluetooth.
  # Experimental = true zeigt den Akkustand von verbundenen Geräten an.
  # FastConnectable reduziert die Verbindungszeit (erhöht aber den Stromverbrauch).
  # AutoEnable schaltet Bluetooth direkt nach dem Booten ein.
  # ==========================================
  hardware.bluetooth = {
    enable      = true;
    powerOnBoot = true;
    settings = {
      General = {
        Experimental    = true;
        FastConnectable = true;
      };
      Policy = {
        AutoEnable = true;
      };
    };
  };


  # ==========================================
  # ZRAM AKTIVIERUNG / RAM KOMPREMIERUNG
  # ==========================================

  mySystem.zramSwap = {
    enable        = true;
    algorithm     = "zstd";    # Der Standard, guter Kompromiss ggfs auf lz4 wechseln
    memoryPercent = 50;        # Maximal 50% des RAMs für zram
    priority      = 100;       # Höher als die SSD-Swap-Priorität (z.B. -1)
  };

  # ==========================================
  # AUTO-LOGIN (nur nach Boot, nicht nach Logout)
  # ==========================================
  # WICHTIG: Wenn du das autologin.nix-Modul verwendest, dann
  # KOMMENTIERE DIE FOLGENDEN ZWEI ZEILEN AUS!
  #
  # Grund: Das autologin.nix-Modul aktiviert den Auto-Login NUR
  # einmalig nach dem Boot. Diese Zeilen hier würden ihn DAUERHAFT
  # aktivieren – auch nach einem manuellen Logout.
  # ==========================================
  # services.displayManager.autoLogin.enable = true;
  # services.displayManager.autoLogin.user   = "luisek03";

  # ==========================================
  # LAPTOP-SPEZIFISCHE PAKETE
  # ==========================================
  # Pakete, die NUR auf dem Laptop installiert werden sollen.
  # (Später z.B. powertop für Energieverwaltung, tlp für Akku-Optimierung)
  #
  # TIPP: Du kannst die Liste der gemeinsamen Pakete aus common/default.nix
  # mit lib.subtractLists oder lib.mkForce anpassen, falls du z.B. Firefox
  # auf dem Laptop nicht haben möchtest.
  # ==========================================
  # flatpak

  services.flatpak.enable = true;
  xdg.portal.enable       = true;


  # ==========================================
  # ENERGIEVERWALTUNG (optional)
  # ==========================================
  # power-profiles-daemon ist der moderne Weg für Energieprofile
  # (powersave, balanced, performance). Viele Laptops brauchen das für
  # eine gute Akkulaufzeit.
  # ==========================================
  # services.power-profiles-daemon.enable = true;

  # ==========================================
  #  WLAN-FIRMWARE (falls nicht in common enthalten)
  # ==========================================
  # Manche Laptops brauchen zusätzliche Firmware für WLAN-Chips.
  # Falls dein WLAN nicht funktioniert, aktiviere diese Zeile:
  # ==========================================
  # hardware.enableRedistributableFirmware = true;


  # ==========================================
  # Laptop-spezifische Eco-Update-Einstellungen
  # ==========================================

  #mySystem.autoGC = {   # wird vermutlich entfernt
  #  maxUsed = 85;          # Laptop hat weniger Speicher
  #  deleteOlderThan = "14d"; # Laptop braucht weniger alte Generationen
  #};

  mySystem.ops.update = {
    enable     = true;
    retries    = 0;
    retryDelay = 10;

    cacheCheck = {
      enable = true;
      # input und caches erben vom Default
    };

    flakeLockBackup = {
      enable     = true;
      autoCommit = true;
    };

    # Post-Update-Hook: Shell-String, wird per bash -c ausgeführt
    postUpdate = {
      enable = true;
      script = "eco-gc-retention";
    };
  };

  # Teil 1: Retention — nur Binary bereitstellen
  mySystem.ops.gc.retention = {
    enable               = true;
    keepDays             = 7;
    minGenerations       = 4;
    safetyHours          = 24;
    maxSafetyGenerations = 20;
  };

    # Teil 2: Collect — Binary + Timer
  mySystem.ops.gc.collect = {
    enable       = true;
    startPercent = 85;
    targetPercent = 80;
    #maxIterations = 3;
    #checkPath = "/nix/store"; ist bereits default
    #schedule = "daily";   # "daily" / "weekly" / "never"
    #schedule erbt jz von ops/common.nix default daily
  };



  # ==========================================
  # IDE AKTIVIEREN (Bool)
  # ==========================================
  mySystem.ide = {
    enable   = true;   # <-- auf false setzen, um IDE zu deaktivieren
    repoUrl  = "git@github.com:luisek03/Eco-System.git";
    repoPath = "/home/luisek03/Projekte/Eco-System";
    userName = "luisek03";
  };

  # ==========================================
  # Aktivierung von steam und andere games launcher
  # ==========================================

  mySystem.steam.enable = true;

}
