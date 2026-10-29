{ ... }:
{
  # Zieht die Options UND den LTS-Fallback rein.
  # Alle CachyOS-Kernel-Dateien importieren diese eine Zeile,
  # statt den Host mit zwei Imports zu belasten.
  imports = [ ../default.nix ];
}
