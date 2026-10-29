# /etc/nixos/Eco-System/modules/games/steam.nix
{ config, pkgs, lib, ... }:

let
  cfg = config.mySystem.steam;
in
{
  # ==========================================
  # BASIS IMPORTIEREN
  # ==========================================
  # Holt GameMode, 32-Bit-Grafik, gamescope und die
  # Option für erlaubte unfreie Paket-Präfixe.
  # Wird auch von anderen Launcher-Modulen importiert –
  # Nix dedupliziert nach Pfad.
  # ==========================================
  imports = [ ./common.nix ];

  # ==========================================
  # OPTIONEN
  # ==========================================
  options.mySystem.steam = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Enable Steam, Proton-GE, and GameMode.";
    };
  };

  # ==========================================
  # UMSETZUNG (nur wenn aktiviert)
  # ==========================================
  config = lib.mkIf cfg.enable {

    # ==========================================
    # UNFREIE PAKETE FÜR STEAM
    # ==========================================
    # "steam" als Präfix erlaubt alles, was mit "steam" beginnt:
    #   steam, steam-original, steam-unwrapped, steamcmd, steam-run, ...
    #
    # Wird in die gemeinsame Option gemerged. Spätere Launcher
    # (lutris, heroic) können weitere Präfixe beitragen.
    # ==========================================
    mySystem.games.allowedUnfreePrefixes = [ "steam" ];

    programs.steam = {
      enable = true;

      # Proton-GE deklarativ als Kompatibilitätstool bereitstellen
      extraCompatPackages = with pkgs; [ proton-ge-bin ];

      # Firewall für Steam Remote Play öffnen
      remotePlay.openFirewall = true;

      # ==========================================
      # ZUSÄTZLICHE LAUFZEIT-PAKETE FÜR STEAM
      # [ACHTUNG: ALLES NUR INTERN IN DER STEAM-UMGEBUNG ERREICHBAR]
      # ==========================================
      package = pkgs.steam.override {
        extraPkgs = pkgs': with pkgs'; [
          # 1. GameMode & Gamescope (für Startoptionen wie
          #    "gamemoderun gamescope ... -- %command%")
          gamemode
          gamescope

          # 2. Wichtige Multimedia-Bibliotheken für Video-Dekodierung & Audio
          ffmpeg
          libvorbis
          libpulseaudio

          # 3. Grundlegende X11-Bibliotheken
          libxcursor
          libxi
          libxinerama
          libxscrnsaver

          # 4. Mauszeiger-Fix
          #    Steam läuft in einem FHS-Container und hat sonst keinen
          #    Zugriff auf das Breeze-Cursor-Theme des Hosts.
          kdePackages.breeze
        ];
      };
    };

    # ==========================================
    # ZUSÄTZLICHE TOOLS (Steam-spezifisch)
    # ==========================================
    environment.systemPackages = with pkgs; [
      protonup-qt   # GUI zum Verwalten von Proton-GE-Versionen
      pulseaudio    # stellt "pactl" bereit (Steam nutzt es für Lautstärke)
      fontconfig    # saubere Font-Konfiguration in der Steam-Umgebung
    ];

    # ==========================================
    # LOCALE-FIX FÜR STEAM
    # ==========================================
    # XOpenIM() in Steam braucht LC_CTYPE; sonst hakt die Anmeldung/GUI.
    # Wird nur gesetzt, wenn Steam aktiv ist (Modul bleibt autark).
    # ==========================================
    i18n.extraLocaleSettings.LC_CTYPE = "en_US.UTF-8";
  };
}
