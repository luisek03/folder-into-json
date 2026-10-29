{ lib, ... }:
{
  options.mySystem.customKernel = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = ''
        Aktiviert den importierten Kernel.

        Wenn false und kernel/default.nix importiert wurde, greift
        der NixOS-LTS-Kernel als Fallback.

        Wenn true, setzt die importierte Kernel-Datei (chaotic,
        lto-v3, lto-zen) den `boot.kernelPackages`. Importiere
        immer nur eine Kernel-Datei, sonst kollidieren die
        Zuweisungen.
      '';
    };

    lts = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = ''
        Wird NUR von chaotic.nix ausgewertet. Alle anderen
        Kernel-Dateien (lto-v3, lto-zen) ignorieren diese Option,
        weil sie immer gegen einen festen CachyOS-Base bauen.
      '';
    };
  };
}
