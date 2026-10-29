# /etc/nixos/Eco-System/modules/games/common.nix
{ config, pkgs, lib, ... }:

let
  # ==========================================
  # GAMING IST AKTIV
  # ==========================================
  # Wird wahr, sobald irgendein Launcher aktiviert ist.
  # Neue Launcher hier ergänzen, sobald sie dazukommen:
  #   || config.mySystem.lutris.enable
  #   || config.mySystem.heroic.enable
  #
  # Dadurch wirkt common.nix nur dann, wenn wirklich
  # gezockt werden soll – sonst bleibt die Maschine
  # schlank (kein 32-Bit-Stack, kein gamemode-Daemon).
  # ==========================================
  gamingEnabled =
    config.mySystem.steam.enable
    # || config.mySystem.lutris.enable
    # || config.mySystem.heroic.enable
    ;
in
{
  # ==========================================
  # GEMEINSAME GAMING-BASIS
  # ==========================================
  # Dieses Modul wird von allen Launcher-Modulen importiert
  # (Steam, Lutris, Heroic, etc.) und stellt die Grundlagen bereit,
  # die jedes Spiel braucht – unabhängig vom Launcher.
  # ==========================================

  # ==========================================
  # OPTIONEN: ERLAUBTE UNFREIE PAKETE
  # ==========================================
  # Jeder Launcher trägt hier seine Namensräume ein.
  # Mehrere Launcher können beitragen, ohne sich zu überschreiben.
  #
  # Statt exakter Paketnamen werden Präfixe genutzt:
  #   "steam" → erlaubt steam, steam-original, steamcmd, steam-run, ...
  #
  # Vorteil: Neue Steam-Pakete in nixpkgs werden automatisch
  # mit erlaubt, ohne dass die Liste gepflegt werden muss.
  # Nachteil: Erlaubt auch unbekannte Pakete im Namensraum.
  #           Für Gaming-Launcher mit klaren Präfixen ist das
  #           unproblematisch.
  # ==========================================
  options.mySystem.games.allowedUnfreePrefixes = lib.mkOption {
    type = lib.types.listOf lib.types.str;
    default = [];
    description = ''
      Liste von Paket-Präfixen, deren unfreie Pakete erlaubt werden.

      Beispiel:
        [ "steam" "lutris" "heroic" ]

      Der Predicate erlaubt jedes unfreie Paket, dessen Name mit
      einem der hier gelisteten Präfixe beginnt.
    '';
    example = [ "steam" "lutris" ];
  };

  config = lib.mkIf gamingEnabled {

    # ==========================================
    # UNFREIE PAKETE (PRÄFIX-MATCH)
    # ==========================================
    # Erlaubt nur unfreie Pakete, deren Name mit einem der
    # Präfixe aus mySystem.games.allowedUnfreePrefixes beginnt.
    #
    # lib.hasPrefix prüft "beginnt mit".
    # lib.any prüft, ob mindestens ein Präfix zutrifft.
    # lib.getName extrahiert den Paketnamen (ohne Version/Hash).
    # ==========================================
    nixpkgs.config.allowUnfreePredicate = pkg:
      let
        name = lib.getName pkg;
      in
      lib.any (prefix: lib.hasPrefix prefix name)
        config.mySystem.games.allowedUnfreePrefixes;

    # ==========================================
    # 32-BIT-SYSTEMBIBLIOTHEKEN
    # ==========================================
    # Wird von allen 32-Bit-Spielen benötigt (Steam Runtime, Wine, etc.)
    # ==========================================
    hardware.graphics = {
      enable = true;
      enable32Bit = true;
    };

    # ==========================================
    # GAMEMODE (Der "GameBooster")
    # ==========================================
    # Optimiert CPU-Governor und I/O-Priorität während des Spielens.
    # inhibit_screensaver verhindert Fehlermeldungen ohne Bildschirmschoner.
    # ==========================================
    programs.gamemode = {
      enable = true;
      settings.general.inhibit_screensaver = 1;
    };

    # ==========================================
    # ZUSÄTZLICHE TOOLS FÜR MANUELLE NUTZUNG
    # ==========================================
    # Im Terminal verfügbar – ergänzend zu extraPkgs in den Launchern.
    # ==========================================
    environment.systemPackages = lib.mkAfter (with pkgs; [
      gamemode      # gamemoderun (für Startoptionen & Terminal)
      gamescope     # gamescope (für Startoptionen & Terminal)
    ]);
  };
}
