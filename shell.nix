{ pkgs ? import <nixpkgs> { } }:

pkgs.mkShell {
  name = "folder-into-json";

  packages = with pkgs; [
    python3      # für folder_into_json.py (nur stdlib nötig)
    jq           # zum Durchsuchen/Prüfen der erzeugten JSON-Datei
  ];

  shellHook = ''
    echo "folder-into-json dev shell"
    echo "  python3 $(python3 --version | cut -d' ' -f2)"
    echo "  jq      $(jq --version)"
    echo ""
    echo "Beispiele:"
    echo "  python folder_into_json.py pack   ./Eco-System Eco-System.json -v"
    echo "  python folder_into_json.py unpack Eco-System.json ./restored"
    echo "  jq '.files[].path' Eco-System.json"
  '';
}
