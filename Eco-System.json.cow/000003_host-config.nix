# /etc/nixos/host-config.nix
# ==========================================
# SINGLE SOURCE OF TRUTH
# ==========================================
# Diese Datei bestimmt, welcher Host gebaut wird.
# Ändere "name" und "host", um auf einen anderen Host zu wechseln.
# ==========================================

{
  # Der Hostname, den die Flake für nixosConfigurations verwendet
  name = "EXAMPLE";

  # Der Ordner unter Eco-System/hosts/, der importiert wird
  host = "/PATH/TO/HOSTS/INIT/FOLDER";
}
