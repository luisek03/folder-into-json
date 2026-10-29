# /etc/nixos/Eco-System/modules/init.nix
# ==========================================
# SYSTEMRELEVANTE OPTIONS
# ==========================================
# Nur Options, die tatsächlich zwischen Modulen wandern.
# Alle anderen Werte (Locale, Zeitzone, Tastatur) stehen direkt
# in default/init.nix – sie werden von keinem Modul gelesen.
# ==========================================

{ config, pkgs, lib, ... }:

{
  options.mySystem = {
    # ==========================================
    # BENUTZER
    # ==========================================
    # userName wird gelesen von:
    #   - modules/system/ops/common.nix (git author email)
    #   - modules/system/ops/update.nix (--user Argument)
    #   - modules/init.nix selbst (paths.repo Default)
    #
    # userFullName wird gelesen von:
    #   - modules/system/ops/common.nix (git author name)
    #
    # Wichtig: Auch users.users.<name> und SSH-Keys sollten diesen
    # Wert nutzen, nicht das Literal "luisek03". Sonst ist der Name
    # doppelt gepflegt.
    # ==========================================
    userName = lib.mkOption {
      type = lib.types.str;
      default = "luisek03";
      description = ''
        Primärer Benutzername.
        Wird für Git-Commits, eco-update und Benutzer-Deklaration genutzt.
      '';
    };

    userFullName = lib.mkOption {
      type = lib.types.str;
      default = "Luis Fernando Meyer";
      description = ''
        Voller Name des Benutzers.
        Wird als Git-Autor-Name und Beschreibung in users.users genutzt.
      '';
    };

    # ==========================================
    # PFADE
    # ==========================================
    # paths.repo ist die Schnittstelle zwischen Modulen und
    # Repo-Struktur. Es wird gelesen von:
    #   - modules/system/ops/common.nix (flakeLockBackup.repoPath)
    #   - modules/userland/nixos_ide.nix (eco-Aliase, deploy-Aliase)
    #   - zukünftigen Deploy-Skripten und eco-update-Hooks
    #
    # Der Wert ist pro Nutzer unterschiedlich. Profile können ihn
    # überschreiben (z. B. profile/<user>/default.nix mit mkForce).
    # ==========================================
    paths = {
      repo = lib.mkOption {
        type = lib.types.str;
        default = "/home/${config.mySystem.userName}/Projekte/Eco-System";
        description = ''
          Pfad zum Git-Repo des Nutzers.

          Wird von eco-update, IDE-Aliasen und Deploy-Skripten genutzt.
          Kann pro Profil überschrieben werden (siehe profile/<user>).

          Das Repo muss nicht auf einem Server liegen – ein lokales
          Git-Repository reicht. Es dient der Versionskontrolle der
          eigenen Konfiguration.
        '';
      };
    };
  };


  options.mySystem.caches = {
    substituters = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [];
      description = ''
        Zusätzliche Substituter, die Module beitragen.
        Werden von finalized.nix in nix.settings.extra-substituters aufgelöst.
        Alle Beiträge werden gemergt (types.listOf, gleiche Priorität).
      '';
    };

    trustedKeys = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [];
      description = ''
        Trusted Public Keys zu den Substitutern.
        Werden von finalized.nix in nix.settings.extra-trusted-public-keys aufgelöst.
      '';
    };
  };
}
