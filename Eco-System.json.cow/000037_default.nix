# /etc/nixos/Eco-System/profile/base/default.nix
# ==========================================
# DISTRO-FUNDAMENT
# ==========================================
# Priorität: lib.mkOverride 1200
# (kleinere Zahl = stärkere Priorität)
#   50  mkForce
#  100  normale Zuweisung
# 1000  mkDefault (profile/luis-eco)
# 1200  ← profile/base (hier)
# 1500  Option-Default
# ==========================================
# Skalare: lib.mkOverride 1200 (überschreibbar durch luis-eco + Host)
# Listen/Attrsets: lib.mkDefault 1000 (merge mit luis-eco + Host)
# ==========================================

{ config, pkgs, lib, ... }:

let
  prio = 1200;   # nur für Skalare
in
{
  imports = [
    ../../modules/system/ops
    ../../modules/system/kernel
    ../../modules/system/zram-swap.nix
  ];

  config = {
    # ==========================================
    # BOOT
    # ==========================================
    boot.loader.systemd-boot.enable      = lib.mkOverride prio true;
    boot.loader.efi.canTouchEfiVariables = lib.mkOverride prio true;
    boot.tmp.useTmpfs                    = lib.mkOverride prio true;
    boot.tmp.cleanOnBoot                 = lib.mkOverride prio true;
    boot.supportedFilesystems            = [ "ntfs3" ];

    # ==========================================
    # NETZWERK (Default — Host überschreibt Hostname)
    # ==========================================
    networking.hostName              = lib.mkOverride prio "nixos";
    networking.networkmanager.enable = lib.mkOverride prio true;

    # ==========================================
    # SSH SERVER
    # ==========================================
    services.openssh = {
      enable                                = lib.mkOverride prio true;
      settings.PasswordAuthentication       = lib.mkOverride prio false;
      settings.KbdInteractiveAuthentication = lib.mkOverride prio false;
      settings.PermitRootLogin              = lib.mkOverride prio "no";
    };

    # ==========================================
    # GRAFIK / DESKTOP (Plasma)
    # ==========================================
    services.xserver.enable                = lib.mkOverride prio true;
    services.displayManager.sddm.enable    = lib.mkOverride prio true;
    services.desktopManager.plasma6.enable = lib.mkOverride prio true;

    # ==========================================
    # DRUCKEN
    # ==========================================
    services.printing.enable = lib.mkOverride prio true;

    # ==========================================
    # SOUND (PipeWire)
    # ==========================================
    services.pulseaudio.enable = lib.mkOverride prio false;
    security.rtkit.enable      = lib.mkOverride prio true;
    services.pipewire = {
      enable            = lib.mkOverride prio true;
      alsa.enable       = lib.mkOverride prio true;
      alsa.support32Bit = lib.mkOverride prio true;
      pulse.enable      = lib.mkOverride prio true;
    };

    # ==========================================
    # LOCALE-DEFAULTS (distro = English — luis-eco überschreibt)
    # ==========================================
    time.timeZone      = lib.mkOverride prio "UTC";
    i18n.defaultLocale = lib.mkOverride prio "en_US.UTF-8";
    i18n.extraLocaleSettings = lib.mkOverride prio {
      LC_CTYPE = "en_US.UTF-8";   # Kompatibilität für XOpenIM etc.
    };

    # ==========================================
    # TASTATUR-DEFAULT (US — luis-eco überschreibt)
    # ==========================================
    console.keyMap               = lib.mkOverride prio "us";
    services.xserver.xkb.layout  = lib.mkOverride prio "us";
    services.xserver.xkb.variant = lib.mkOverride prio "";

    # ==========================================
    # ZRAM AKTIVIERUNG / RAM KOMPREMIERUNG
    # ==========================================

    mySystem.zramSwap = {
        enable = lib.mkOverride prio true;
        algorithm = lib.mkOverride prio "lz4";    # Der Standard, guter Kompromiss ggfs auf lz4 wechseln
        memoryPercent = lib.mkOverride prio 50;    # Maximal 50% des RAMs für zram
        priority = lib.mkOverride prio 100;        # Höher als die SSD-Swap-Priorität (z.B. -1)
    };


    # ==========================================
    # NIX SETTINGS
    # ==========================================
    # Kritische Infrastruktur: Flakes MÜSSEN funktionieren.
    # mkForce auf genau diesen Key — kann von nichts überstimmt werden.
    #
    # Restliche Defaults — mergebar mit Profilen und Host.
    # lib.mkMerge führt beide Definitionen in EINEM nix.settings-Block zusammen.
    # Caches — als Beitrag zur mySystem.caches-Option
    mySystem.caches.substituters = [
      "https://cache.nixos.org"
      "https://nyx-cache.chaotic.cx"
      "https://nix-community.cachix.org"
      "https://mic92.cachix.org"
    ];

    mySystem.caches.trustedKeys = [
      "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY="
      "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
      "nyx-cache.chaotic.cx:dJxTrgMC3V3cFfyIiBQDQorG6k1LsqurH/srpMSq7qk="
      "mic92.cachix.org-1:gi8IhgiT3CYZnJsaW7fxznzTkMUOn1RY4GmXdT/nXYQ="
    ];

    # Rest von nix.settings bleibt wie gehabt
    # (experimental-features, accept-flake-config, max-jobs, …)
    nix.settings = lib.mkMerge [
      { experimental-features = lib.mkForce [ "nix-command" "flakes" ]; }
      (lib.mkDefault {
        accept-flake-config   = true;
        max-jobs              = 4;
        cores                 = 0;
        connect-timeout       = 10;
        download-attempts     = 3;
        max-substitution-jobs = 32;
        http-connections      = 32;
      })
    ];

    nix.nixPath        = lib.mkOverride prio [ "nixpkgs=flake:nixpkgs" ];
    nix.channel.enable = lib.mkOverride prio false;

    # ==========================================
    # DOKUMENTATION
    # ==========================================
    documentation.enable       = lib.mkOverride prio false;
    documentation.nixos.enable = lib.mkOverride prio false;

    # ==========================================
    # BASISPACKETE (KDE / Essentials)
    # ==========================================
    # mkDefault → mergt mit luis-eco + Host.
    environment.systemPackages = with pkgs; [
      git
      nano

      # KDE / Plasma-Werkzeuge
      kdePackages.dolphin
      kdePackages.kio
      kdePackages.kio-fuse
      kdePackages.kio-extras
      kdePackages.kdenetwork-filesharing
      kdePackages.kfind
      kdePackages.partitionmanager
      kdePackages.bluedevil

      ];

    # ==========================================
    # BASIS-ALIASE (sinnvolle Distro-Defaults)
    # ==========================================
    # mkDefault → mergt mit luis-eco + Host.
    environment.shellAliases = {
      ll        = "ls -al --color=auto";
      cls       = "clear";
      watch     = "watch -p";
      cp        = "cp --reflink=auto";
      fastfetch = "nix-shell -p fastfetch --run fastfetch";
    };
  };
}
