# modules/features/zram-swap.nix
{ config, lib, pkgs, ... }:

let
  cfg = config.mySystem.zramSwap;
in
{
  options.mySystem.zramSwap = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = ''
        Aktiviert zram-basierten Swap.
        zram erstellt ein komprimiertes Block-Device im RAM, das als
        zusätzlicher Swap-Speicher dient. Es wird nur dann genutzt,
        wenn der physische RAM knapp wird, und schont so die SSD.
      '';
    };

    algorithm = lib.mkOption {
      type = lib.types.enum [ "lzo" "lz4" "lz4hc" "zstd" "deflate" "842" ];
      default = "zstd";
      description = ''
        Der Komprimierungsalgorithmus für zram.

        - zstd: Beste Kompromiss aus Kompressionsrate und Geschwindigkeit (Empfohlen).
        - lz4:  Sehr schnell, aber geringere Kompressionsrate. Gut für reaktionsschnelle Systeme.
        - lzo:  Gute Kompression, aber langsamer als lz4.
        - Weitere: lz4hc (höhere Kompression, langsamer), deflate, 842.
      '';
      example = "lz4";
    };

    memoryPercent = lib.mkOption {
      type = lib.types.int;
      default = 50;
      description = ''
        Die maximale Menge an Speicher (in Prozent des Gesamt-RAMs),
        die das zram-Gerät belegen darf.
        Hinweis: Dies ist die Größe *vor* der Komprimierung.
        Bei 16 GB RAM und 50% können bis zu 8 GB unkomprimierte Daten
        im zram-Gerät liegen, die physisch weniger Platz einnehmen.
      '';
      example = 30;
    };

    priority = lib.mkOption {
      type = lib.types.int;
      default = 100;
      description = ''
        Die Priorität des zram-Swap-Geräts.
        Der Kernel nutzt Swap-Geräte mit höherer Priorität zuerst.
        Dieser Wert sollte **höher** sein als die Priorität deiner
        SSD-Swap-Partition (üblich sind hier -1 oder -2), damit
        zram zuerst gefüllt wird und die SSD nur als letzter Ausweg dient.
      '';
      example = 200;
    };
  };

  config = lib.mkIf cfg.enable {
    zramSwap = {
      enable = true;
      inherit (cfg) algorithm memoryPercent priority;
    };

    # Explizite Warnung, falls die Priorität nicht höher ist als die der SSD.
    warnings = lib.optionals (cfg.priority <= 0) [
      "mySystem.zramSwap.priority ist auf ${toString cfg.priority} gesetzt. "
      "Dies ist möglicherweise niedriger als die Priorität deiner SSD-Swap-Partition. "
      "Der Kernel könnte dann die SSD anstelle von zram nutzen. "
      "Ein Wert über 0 (z.B. 100) wird empfohlen."
    ];
  };
}
